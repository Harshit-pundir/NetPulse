from datetime import datetime, timedelta
from sqlalchemy import select
from ..models import MonitoringResult


def uptime_for(session, device_id, hours):
    start = datetime.utcnow() - timedelta(hours=hours)
    rows = session.scalars(select(MonitoringResult).where(MonitoringResult.device_id == device_id, MonitoringResult.checked_at >= start, MonitoringResult.status != "MONITOR_ERROR")).all()
    if not rows: return None
    successful = sum(row.status in ("ONLINE", "WARNING", "CRITICAL") for row in rows)
    return round(successful / len(rows) * 100, 2)
