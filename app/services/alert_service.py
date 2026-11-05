from datetime import datetime
from sqlalchemy import select
from ..models import ActivityLog, Alert


def create_alert(session, device, alert_type, severity, message):
    active = session.scalar(select(Alert).where(Alert.device_id == device.id, Alert.alert_type == alert_type, Alert.acknowledged.is_(False)))
    if active:
        if severity == "CRITICAL": active.severity, active.message = severity, message
        return active
    alert = Alert(device_id=device.id, alert_type=alert_type, severity=severity, message=message)
    session.add_all([alert, ActivityLog(device_id=device.id, event_type=alert_type, message=message)])
    return alert


def acknowledge_active_alerts(session, device_id, alert_type):
    rows = session.scalars(select(Alert).where(Alert.device_id == device_id, Alert.alert_type == alert_type, Alert.acknowledged.is_(False))).all()
    for alert in rows:
        alert.acknowledged, alert.acknowledged_at = True, datetime.utcnow()
        session.add(ActivityLog(device_id=device_id, event_type="ALERT_RESOLVED", message=f"Alert resolved: {alert.message}"))


def process_transition(session, device, old_status, new_status, latency):
    was_up = old_status in ("ONLINE", "WARNING", "CRITICAL")
    is_up = new_status in ("ONLINE", "WARNING", "CRITICAL")
    if was_up and new_status == "OFFLINE": create_alert(session, device, "DEVICE_DOWN", "CRITICAL", f"{device.name} is unreachable.")
    if old_status == "OFFLINE" and is_up:
        create_alert(session, device, "DEVICE_RECOVERED", "INFO", f"{device.name} has recovered.")
        acknowledge_active_alerts(session, device.id, "DEVICE_DOWN")
    if new_status in ("WARNING", "CRITICAL") and old_status not in ("WARNING", "CRITICAL") or new_status == "CRITICAL" and old_status == "WARNING":
        severity = "CRITICAL" if new_status == "CRITICAL" else "WARNING"
        create_alert(session, device, "HIGH_LATENCY", severity, f"{device.name} latency is {latency:.1f} ms.")
    if new_status not in ("WARNING", "CRITICAL"): acknowledge_active_alerts(session, device.id, "HIGH_LATENCY")
