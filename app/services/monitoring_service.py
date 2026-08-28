import platform, re, subprocess, threading, time, logging
from datetime import datetime
from flask import current_app
from ..extensions import db
from ..models import Device, MonitoringResult, ActivityLog
from .alert_service import process_transition

log = logging.getLogger(__name__)
_scheduler_started = False

def ping_host(host, timeout=2):
    system = platform.system().lower()
    command = ['ping', '-n' if system == 'windows' else '-c', '1', '-w' if system == 'windows' else '-W', str(int(timeout * 1000) if system == 'windows' else max(1, int(timeout))), host]
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 2)
        output = (completed.stdout or '') + (completed.stderr or '')
        match = re.search(r'(?:time[=<]|Average = )\s*([\d.]+)\s*ms', output, re.I)
        latency = float(match.group(1)) if match else round((time.perf_counter()-started)*1000, 2)
        return completed.returncode == 0, latency if completed.returncode == 0 else None, None if completed.returncode == 0 else output[-300:]
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, None, str(exc)

def classify_latency(latency, warning, critical):
    if latency is None: return 'OFFLINE'
    return 'WARNING' if latency > warning else 'ONLINE'

def monitor_device(device):
    old = device.status
    reachable, latency, error = ping_host(device.ip_address)
    status = classify_latency(latency if reachable else None, current_app.config['LATENCY_WARNING_MS'], current_app.config['LATENCY_CRITICAL_MS'])
    now = datetime.utcnow()
    device.status, device.current_latency, device.last_checked_at = status, latency, now
    db.session.add(MonitoringResult(device_id=device.id,status=status,latency=latency,response_time=latency,checked_at=now,error_message=error))
    if old != status:
        process_transition(device, old, status, latency or 0)
        db.session.add(ActivityLog(device_id=device.id,event_type='STATUS_CHANGE',message=f'{device.name}: {old} → {status}'))
    db.session.commit()
    return status

def monitor_all_devices():
    for device in Device.query.filter_by(monitoring_enabled=True).all():
        try: monitor_device(device)
        except Exception:
            db.session.rollback(); log.exception('Monitoring failed for device %s', device.id)

def start_scheduler(app):
    global _scheduler_started
    if _scheduler_started: return
    _scheduler_started = True
    def worker():
        with app.app_context():
            while True:
                monitor_all_devices(); time.sleep(app.config['MONITOR_INTERVAL'])
    threading.Thread(target=worker, daemon=True, name='netpulse-monitor').start()
    log.info('Monitoring worker started')
