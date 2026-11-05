from datetime import datetime, timedelta, timezone
from app.database import supabase


def uptime_for(device_id: int, hours: int) -> float | None:
    """Calculate reachable checks as a percentage for the selected period."""
    start = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    result = (
        supabase.table("monitoring_results")
        .select("status")
        .eq("device_id", device_id)
        .gte("checked_at", start)
        .neq("status", "MONITOR_ERROR")
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None
    successful = sum(row["status"] in {"ONLINE", "WARNING", "CRITICAL"} for row in rows)
    return round(successful / len(rows) * 100, 2)
