from ..extensions import db
from ..models import Alert, ActivityLog

def create_alert(device, alert_type, severity, message):
    existing = Alert.query.filter_by(device_id=device.id, alert_type=alert_type, acknowledged=False).first()
    if existing: return existing
    alert = Alert(device_id=device.id, alert_type=alert_type, severity=severity, message=message)
    db.session.add(alert)
    db.session.add(ActivityLog(device_id=device.id, event_type=alert_type, message=message))
    return alert

def process_transition(device, old_status, new_status, latency):
    if old_status in ('ONLINE','WARNING') and new_status == 'OFFLINE':
        create_alert(device, 'DEVICE_DOWN', 'CRITICAL', f'{device.name} is unreachable.')
    elif old_status == 'OFFLINE' and new_status in ('ONLINE','WARNING'):
        create_alert(device, 'DEVICE_RECOVERED', 'INFO', f'{device.name} has recovered.')
        for a in Alert.query.filter_by(device_id=device.id, alert_type='DEVICE_DOWN', acknowledged=False): a.acknowledged = True
    if new_status == 'WARNING' and old_status != 'WARNING':
        create_alert(device, 'HIGH_LATENCY', 'WARNING', f'{device.name} latency is {latency:.1f} ms.')
    if new_status != 'WARNING':
        for a in Alert.query.filter_by(device_id=device.id, alert_type='HIGH_LATENCY', acknowledged=False): a.acknowledged = True
