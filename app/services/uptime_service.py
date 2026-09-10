from datetime import datetime, timedelta

from ..models import MonitoringResult


def uptime_for(device_id, hours):
    """Return the percentage of successful checks in the selected time window."""
    start_time = datetime.utcnow() - timedelta(hours=hours)
    results = MonitoringResult.query.filter_by(device_id=device_id).filter(
        MonitoringResult.checked_at >= start_time
    ).all()

    total_checks = len(results)
    if total_checks == 0:
        return None

    online_checks = 0
    for result in results:
        if result.status in ("ONLINE", "WARNING"):
            online_checks += 1

    # A warning is still a successful reachability check.
    return round((online_checks / total_checks) * 100, 2)
