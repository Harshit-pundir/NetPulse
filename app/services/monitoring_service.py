"""Ping monitored devices and save results through the shared Supabase client."""
import logging
import os
import platform
import re
import subprocess
import threading
import time
from datetime import datetime, timezone

from app.database import supabase
from app.services.alert_service import process_transition

log = logging.getLogger(__name__)
_worker_lock = threading.Lock()


def should_start_monitoring(app, _use_reloader=False):
    return app.state.config.get("START_MONITORING", True) and not app.state.config.get("TESTING", False)


def ping_host(host: str, timeout: int = 2):
    """Run one system ping and return reachability, latency, and an error."""
    is_windows = platform.system().lower() == "windows"
    command = ["ping", "-n" if is_windows else "-c", "1", "-w" if is_windows else "-W",
               str(timeout * 1000 if is_windows else timeout), host]
    started = time.perf_counter()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 2)
    except (subprocess.TimeoutExpired, OSError) as error:
        return False, None, f"MONITOR_ERROR: {error}"

    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode:
        return False, None, output[-300:]
    match = re.search(r"(?:time[=<]|Average = )\s*([\d.]+)\s*ms", output, re.IGNORECASE)
    latency = float(match.group(1)) if match else round((time.perf_counter() - started) * 1000, 2)
    return True, latency, None


def classify_latency(latency, warning_threshold, critical_threshold):
    if latency is None:
        return "OFFLINE"
    if latency > critical_threshold:
        return "CRITICAL"
    if latency > warning_threshold:
        return "WARNING"
    return "ONLINE"


def monitor_device(device: dict, config=None) -> str:
    """Check one device, record its result, update it, and apply alert rules."""
    old_status = device.get("status", "UNKNOWN")
    reachable, latency, error = ping_host(device["ip_address"])
    checked_at = datetime.now(timezone.utc).isoformat()

    if error and error.startswith("MONITOR_ERROR:"):
        supabase.table("monitoring_results").insert({
            "device_id": device["id"], "status": "MONITOR_ERROR",
            "checked_at": checked_at, "error_message": error.removeprefix("MONITOR_ERROR: ")[:500],
        }).execute()
        return "MONITOR_ERROR"

    if not reachable:
        latency = None
    settings = config or {}
    warning = float(settings.get("LATENCY_WARNING_MS", os.getenv("LATENCY_WARNING_MS", 100)))
    critical = float(settings.get("LATENCY_CRITICAL_MS", os.getenv("LATENCY_CRITICAL_MS", 200)))
    status = classify_latency(latency, warning, critical)

    supabase.table("monitoring_results").insert({
        "device_id": device["id"], "status": status, "latency": latency,
        "response_time": latency, "checked_at": checked_at, "error_message": error,
    }).execute()
    supabase.table("devices").update({
        "status": status, "current_latency": latency, "last_checked_at": checked_at,
        "updated_at": checked_at,
    }).eq("id", device["id"]).execute()
    device["status"] = status

    if status != old_status:
        process_transition(device, old_status, status, latency or 0)
        supabase.table("activity_logs").insert({
            "device_id": device["id"], "event_type": "STATUS_CHANGE",
            "message": f"{device['name']}: {old_status} -> {status}",
            "created_at": checked_at,
        }).execute()
    return status


def monitor_all_devices(stop_event=None, config=None):
    """Fetch enabled devices and check each one; one failure does not stop others."""
    try:
        devices = supabase.table("devices").select("*").eq("monitoring_enabled", True).execute().data or []
    except Exception:
        log.exception("Could not fetch devices for monitoring")
        return

    for device in devices:
        if stop_event and stop_event.is_set():
            break
        try:
            monitor_device(device, config)
        except Exception:
            log.exception("Monitoring failed for device %s", device.get("id", "unknown"))


def start_scheduler(app):
    """Start one daemon thread which checks devices at the configured interval."""
    with _worker_lock:
        if getattr(app.state, "monitoring_started", False):
            return False
        stop_event = threading.Event()
        app.state.monitoring_stop = stop_event

        def worker():
            while not stop_event.is_set():
                monitor_all_devices(stop_event, app.state.config)
                stop_event.wait(max(1, int(app.state.config.get("MONITOR_INTERVAL", 10))))

        thread = threading.Thread(target=worker, daemon=True, name="netpulse-monitor")
        app.state.monitoring_thread = thread
        app.state.monitoring_started = True
        thread.start()
    return True


def stop_scheduler(app, timeout=5):
    """Tell the worker to stop and wait for no more than five seconds."""
    event = getattr(app.state, "monitoring_stop", None)
    thread = getattr(app.state, "monitoring_thread", None)
    if event is None or thread is None:
        return True
    event.set()
    thread.join(min(max(0, timeout), 5))
    return not thread.is_alive()
