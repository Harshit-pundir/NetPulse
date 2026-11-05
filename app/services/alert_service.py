"""Create, update, and resolve alerts through the shared Supabase client."""
from datetime import datetime, timezone
from app.database import supabase


def _add_activity(device_id: int, event_type: str, message: str) -> None:
    supabase.table("activity_logs").insert({
        "device_id": device_id, "event_type": event_type, "message": message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def create_alert(device: dict, alert_type: str, severity: str, message: str) -> dict:
    active = (supabase.table("alerts").select("*").eq("device_id", device["id"])
              .eq("alert_type", alert_type).eq("acknowledged", False).limit(1).execute().data or [])
    if active:
        alert = active[0]
        if severity == "CRITICAL":
            supabase.table("alerts").update({"severity": severity, "message": message}).eq("id", alert["id"]).execute()
        return alert

    result = supabase.table("alerts").insert({
        "device_id": device["id"], "alert_type": alert_type,
        "severity": severity, "message": message, "acknowledged": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    _add_activity(device["id"], alert_type, message)
    return result.data[0]


def acknowledge_active_alerts(device_id: int, alert_type: str) -> None:
    alerts = (supabase.table("alerts").select("*").eq("device_id", device_id)
              .eq("alert_type", alert_type).eq("acknowledged", False).execute().data or [])
    now = datetime.now(timezone.utc).isoformat()
    for alert in alerts:
        supabase.table("alerts").update({"acknowledged": True, "acknowledged_at": now}).eq("id", alert["id"]).execute()
        _add_activity(device_id, "ALERT_RESOLVED", f"Alert resolved: {alert['message']}")


def process_transition(device: dict, old_status: str, new_status: str, latency: float) -> None:
    was_up = old_status in {"ONLINE", "WARNING", "CRITICAL"}
    is_up = new_status in {"ONLINE", "WARNING", "CRITICAL"}
    if was_up and new_status == "OFFLINE":
        create_alert(device, "DEVICE_DOWN", "CRITICAL", f"{device['name']} is unreachable.")
    if old_status == "OFFLINE" and is_up:
        create_alert(device, "DEVICE_RECOVERED", "INFO", f"{device['name']} has recovered.")
        acknowledge_active_alerts(device["id"], "DEVICE_DOWN")

    entered_slow_state = new_status in {"WARNING", "CRITICAL"} and old_status not in {"WARNING", "CRITICAL"}
    escalated = new_status == "CRITICAL" and old_status == "WARNING"
    if entered_slow_state or escalated:
        severity = "CRITICAL" if new_status == "CRITICAL" else "WARNING"
        create_alert(device, "HIGH_LATENCY", severity, f"{device['name']} latency is {latency:.1f} ms.")
    if new_status not in {"WARNING", "CRITICAL"}:
        acknowledge_active_alerts(device["id"], "HIGH_LATENCY")
