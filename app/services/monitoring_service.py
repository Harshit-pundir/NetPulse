"""Simple background thread that checks devices independently of web requests."""
import logging, os, platform, re, subprocess, threading, time
from datetime import datetime
from sqlalchemy import select
from ..database import SessionLocal
from ..models import ActivityLog, Device, MonitoringResult
from .alert_service import process_transition

log = logging.getLogger(__name__)
_lock = threading.Lock()


def should_start_monitoring(app, use_reloader=False):
    settings = getattr(app.state, "config", {})
    return settings.get("START_MONITORING", True) and not settings.get("TESTING", False)


def ping_host(host, timeout=2):
    windows = platform.system().lower() == "windows"
    command = ["ping", "-n" if windows else "-c", "1", "-w" if windows else "-W", str(int(timeout * 1000) if windows else max(1, int(timeout))), host]
    started = time.perf_counter()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 2)
    except (subprocess.TimeoutExpired, OSError) as error:
        return False, None, f"MONITOR_ERROR: {error}"
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode:
        return False, None, output[-300:]
    match = re.search(r"(?:time[=<]|Average = )\s*([\d.]+)\s*ms", output, re.I)
    return True, float(match.group(1)) if match else round((time.perf_counter()-started)*1000, 2), None


def classify_latency(latency, warning_threshold, critical_threshold):
    if latency is None: return "OFFLINE"
    if latency > critical_threshold: return "CRITICAL"
    if latency > warning_threshold: return "WARNING"
    return "ONLINE"


def monitor_device(device, session=None, config=None):
    """Check a device and save its measurement using its own session."""
    own_session = session is None
    session = session or SessionLocal()
    try:
        device = session.get(Device, device.id)
        if not device: return None
        old_status = device.status
        reachable, latency, error = ping_host(device.ip_address)
        checked = datetime.utcnow()
        if error and error.startswith("MONITOR_ERROR:"):
            session.add(MonitoringResult(device_id=device.id, status="MONITOR_ERROR", checked_at=checked, error_message=error.removeprefix("MONITOR_ERROR: ")[:500]))
            session.commit(); return "MONITOR_ERROR"
        if not reachable: latency = None
        warning = float((config or {}).get("LATENCY_WARNING_MS", os.getenv("LATENCY_WARNING_MS", 100)))
        critical = float((config or {}).get("LATENCY_CRITICAL_MS", os.getenv("LATENCY_CRITICAL_MS", 200)))
        status = classify_latency(latency, warning, critical)
        device.status, device.current_latency, device.last_checked_at = status, latency, checked
        session.add(MonitoringResult(device_id=device.id, status=status, latency=latency, response_time=latency, checked_at=checked, error_message=error))
        if status != old_status:
            process_transition(session, device, old_status, status, latency or 0)
            session.add(ActivityLog(device_id=device.id, event_type="STATUS_CHANGE", message=f"{device.name}: {old_status} -> {status}"))
        session.commit()
        return status
    except Exception:
        session.rollback(); raise
    finally:
        if own_session: session.close()


def monitor_all_devices(stop_event=None, config=None):
    with SessionLocal() as session:
        ids = session.scalars(select(Device.id).where(Device.monitoring_enabled.is_(True))).all()
    for device_id in ids:
        if stop_event and stop_event.is_set(): break
        try:
            with SessionLocal() as session:
                device = session.get(Device, device_id)
                if device: monitor_device(device, session, config)
        except Exception:
            log.exception("Monitoring failed for device %s", device_id)


def start_scheduler(app):
    with _lock:
        if getattr(app.state, "monitoring_started", False): return False
        stop_event = threading.Event(); app.state.monitoring_stop = stop_event
        def worker():
            while not stop_event.is_set():
                monitor_all_devices(stop_event, app.state.config)
                stop_event.wait(max(1, int(app.state.config.get("MONITOR_INTERVAL", 10))))
        thread = threading.Thread(target=worker, daemon=True, name="netpulse-monitor")
        app.state.monitoring_thread = thread; app.state.monitoring_started = True; thread.start()
    return True


def stop_scheduler(app, timeout=5):
    event = getattr(app.state, "monitoring_stop", None); thread = getattr(app.state, "monitoring_thread", None)
    if event is None or thread is None: return True
    event.set(); thread.join(min(max(0, timeout), 5))
    return not thread.is_alive()
