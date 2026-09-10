from ..extensions import db
from ..models import ActivityLog, Alert


def create_alert(device, alert_type, severity, message):
    """Create one active alert of a type, unless it already exists."""
    active_alert = Alert.query.filter_by(device_id=device.id, alert_type=alert_type, acknowledged=False).first()
    if active_alert:
        return active_alert

    alert = Alert(device_id=device.id, alert_type=alert_type, severity=severity, message=message)
    db.session.add(alert)
    db.session.add(ActivityLog(device_id=device.id, event_type=alert_type, message=message))
    return alert


def acknowledge_active_alerts(device_id, alert_type):
    """Close active alerts when the condition is no longer true."""
    alerts = Alert.query.filter_by(device_id=device_id, alert_type=alert_type, acknowledged=False).all()
    for alert in alerts:
        alert.acknowledged = True


def process_transition(device, old_status, new_status, latency):
    """Create alerts only when a device changes health state."""
    was_reachable = old_status in ("ONLINE", "WARNING")
    is_reachable = new_status in ("ONLINE", "WARNING")

    if was_reachable and new_status == "OFFLINE":
        create_alert(device, "DEVICE_DOWN", "CRITICAL", f"{device.name} is unreachable.")

    if old_status == "OFFLINE" and is_reachable:
        create_alert(device, "DEVICE_RECOVERED", "INFO", f"{device.name} has recovered.")
        acknowledge_active_alerts(device.id, "DEVICE_DOWN")

    if new_status == "WARNING" and old_status != "WARNING":
        create_alert(device, "HIGH_LATENCY", "WARNING", f"{device.name} latency is {latency:.1f} ms.")

    if new_status != "WARNING":
        acknowledge_active_alerts(device.id, "HIGH_LATENCY")
