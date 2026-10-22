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
_scheduler_lock = threading.Lock()
_shutdown_timeout = 5


def should_start_monitoring(app, use_reloader):
    """Avoid starting a second worker in Flask's debug reloader parent process."""
    if not app.config.get("START_MONITORING", True) or app.testing:
        return False

    if not use_reloader:
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
        return False, None, f"MONITOR_ERROR: {error}"

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


def classify_latency(latency, warning_threshold, critical_threshold):
    """Convert a ping result into the status displayed in the dashboard."""
    if latency is None:
        return "OFFLINE"
    if latency > critical_threshold:
        return "CRITICAL"
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

    # A local execution error says nothing about the device's health.
    if error_message and error_message.startswith("MONITOR_ERROR:"):
        checked_at = datetime.utcnow()
        db.session.add(MonitoringResult(
            device_id=device.id,
            status="MONITOR_ERROR",
            checked_at=checked_at,
            error_message=error_message.removeprefix("MONITOR_ERROR: ")[:500],
        ))
        db.session.commit()
        return "MONITOR_ERROR"

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


def monitor_all_devices(stop_event=None):
    """Run one monitoring cycle for every enabled device."""
    devices = Device.query.filter_by(monitoring_enabled=True).all()
    for device in devices:
        try:
            if stop_event:
                # Reserve the next check atomically with shutdown. Once shutdown
                # sets the event, no further device check can be reserved.
                with _scheduler_lock:
                    if stop_event.is_set():
                        break
            monitor_device(device)
        except Exception:
            # A failed device check must not stop checks for remaining devices.
            db.session.rollback()
            log.exception("Monitoring failed for device %s", device.id)


def start_scheduler(app):
    """Start one background thread that repeatedly checks all devices."""
    with _scheduler_lock:
        if app.extensions.get("netpulse_monitoring_worker_started"):
            return False

        stop_event = threading.Event()
        app.extensions["netpulse_monitoring_stop_event"] = stop_event

        def worker():
            # Database queries need Flask's application context outside a web request.
            with app.app_context():
                while not stop_event.is_set():
                    try:
                        monitor_all_devices(stop_event)
                    except Exception:
                        # A database outage must not permanently kill the worker thread.
                        db.session.rollback()
                        log.exception("Monitoring cycle failed; it will retry")
                    finally:
                        db.session.remove()
                    stop_event.wait(max(1, app.config["MONITOR_INTERVAL"]))

        thread = threading.Thread(target=worker, daemon=True, name="netpulse-monitor")
        app.extensions["netpulse_monitoring_thread"] = thread
        app.extensions["netpulse_monitoring_worker_started"] = True
        try:
            thread.start()
        except Exception:
            app.extensions["netpulse_monitoring_worker_started"] = False
            app.extensions.pop("netpulse_monitoring_thread", None)
            app.extensions.pop("netpulse_monitoring_stop_event", None)
            raise
    log.info("Monitoring worker started")
    return True


def stop_scheduler(app, timeout=5):
    """Signal the worker to stop and wait for at most five seconds."""
    with _scheduler_lock:
        stop_event = app.extensions.get("netpulse_monitoring_stop_event")
        thread = app.extensions.get("netpulse_monitoring_thread")
        if not stop_event or not thread:
            return False
        stop_event.set()

    if thread is threading.current_thread():
        return False
    try:
        thread.join(min(max(0, timeout), _shutdown_timeout))
    except KeyboardInterrupt:
        # A second Ctrl+C should not cancel the stop signal or cause another
        # shutdown traceback. The daemon worker will finish its current check.
        log.warning("Shutdown wait interrupted; monitoring has been told to stop")
        return False

    if not thread.is_alive():
        return True
    return False
