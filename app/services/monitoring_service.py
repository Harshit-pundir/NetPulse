import logging
import os
import platform
import re
import subprocess
import threading
import time
from datetime import datetime

from flask import current_app

from ..extensions import db
from ..models import ActivityLog, Device, MonitoringResult
from .alert_service import process_transition

log = logging.getLogger(__name__)


def should_start_monitoring(app, debug_mode):
    """Avoid starting a second worker in Flask's debug reloader parent process."""
    if not app.config.get("START_MONITORING", True) or app.testing:
        return False

    if not debug_mode:
        return True

    return os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def ping_host(host, timeout=2):
    """Use the operating system ping command and return reachability and latency."""
    is_windows = platform.system().lower() == "windows"
    count_option = "-n" if is_windows else "-c"
    timeout_option = "-w" if is_windows else "-W"
    timeout_value = int(timeout * 1000) if is_windows else max(1, int(timeout))
    command = ["ping", count_option, "1", timeout_option, str(timeout_value), host]

    started_at = time.perf_counter()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 2)
    except (subprocess.TimeoutExpired, OSError) as error:
        return False, None, str(error)

    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        return False, None, output[-300:]

    match = re.search(r"(?:time[=<]|Average = )\s*([\d.]+)\s*ms", output, re.IGNORECASE)
    if match:
        latency = float(match.group(1))
    else:
        # Some ping versions do not print a parseable time. Use elapsed time instead.
        latency = round((time.perf_counter() - started_at) * 1000, 2)

    return True, latency, None


def classify_latency(latency, warning_threshold, _critical_threshold):
    """Convert a ping result into the status displayed in the dashboard."""
    if latency is None:
        return "OFFLINE"
    if latency > warning_threshold:
        return "WARNING"
    return "ONLINE"


def save_monitoring_result(device, status, latency, error_message, checked_at):
    """Save one check and update the device's latest health information."""
    device.status = status
    device.current_latency = latency
    device.last_checked_at = checked_at

    result = MonitoringResult(
        device_id=device.id,
        status=status,
        latency=latency,
        response_time=latency,
        checked_at=checked_at,
        error_message=error_message,
    )
    db.session.add(result)


def monitor_device(device):
    """Check a single device, save the result, then create needed alerts."""
    old_status = device.status
    reachable, latency, error_message = ping_host(device.ip_address)

    if not reachable:
        latency = None

    status = classify_latency(
        latency,
        current_app.config["LATENCY_WARNING_MS"],
        current_app.config["LATENCY_CRITICAL_MS"],
    )
    checked_at = datetime.utcnow()
    save_monitoring_result(device, status, latency, error_message, checked_at)

    if old_status != status:
        process_transition(device, old_status, status, latency or 0)
        message = f"{device.name}: {old_status} -> {status}"
        db.session.add(ActivityLog(device_id=device.id, event_type="STATUS_CHANGE", message=message))

    db.session.commit()
    return status


def monitor_all_devices():
    """Run one monitoring cycle for every enabled device."""
    devices = Device.query.filter_by(monitoring_enabled=True).all()
    for device in devices:
        try:
            monitor_device(device)
        except Exception:
            # A failed device check must not stop checks for remaining devices.
            db.session.rollback()
            log.exception("Monitoring failed for device %s", device.id)


def start_scheduler(app):
    """Start one background thread that repeatedly checks all devices."""
    if app.extensions.get("netpulse_monitoring_worker_started"):
        return False

    app.extensions["netpulse_monitoring_worker_started"] = True

    def worker():
        # Database queries need Flask's application context outside a web request.
        with app.app_context():
            while True:
                monitor_all_devices()
                time.sleep(app.config["MONITOR_INTERVAL"])

    thread = threading.Thread(target=worker, daemon=True, name="netpulse-monitor")
    thread.start()
    log.info("Monitoring worker started")
    return True
