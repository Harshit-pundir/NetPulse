from datetime import datetime, timedelta
from ..models import MonitoringResult

def uptime_for(device_id, hours):
    since = datetime.utcnow() - timedelta(hours=hours)
    results = MonitoringResult.query.filter_by(device_id=device_id).filter(MonitoringResult.checked_at >= since).all()
    if not results: return None
    return round(100 * sum(r.status in ('ONLINE','WARNING') for r in results) / len(results), 2)
