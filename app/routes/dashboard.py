from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template
from flask_login import login_required

from ..models import ActivityLog, Alert, Device, MonitoringResult
from .helpers import device_json

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    return render_template("dashboard.html")


@bp.get("/api/dashboard/summary")
@login_required
def summary():
    devices = Device.query.all()
    status_counts = {"ONLINE": 0, "OFFLINE": 0, "WARNING": 0, "CRITICAL": 0, "UNKNOWN": 0}
    latency_values = []

    for device in devices:
        status_counts[device.status] = status_counts.get(device.status, 0) + 1
        if device.current_latency is not None:
            latency_values.append(device.current_latency)

    average_latency = None
    if latency_values:
        average_latency = round(sum(latency_values) / len(latency_values), 1)

    return jsonify(
        total=len(devices),
        online=status_counts["ONLINE"],
        offline=status_counts["OFFLINE"],
        warning=status_counts["WARNING"],
        critical=status_counts["CRITICAL"],
        unknown=status_counts["UNKNOWN"],
        active_alerts=Alert.query.filter_by(acknowledged=False).count(),
        average_latency=average_latency,
        devices=[device_json(device) for device in devices],
    )


@bp.get("/api/dashboard/latency")
@login_required
def latency():
    start_time = datetime.utcnow() - timedelta(hours=24)
    results = MonitoringResult.query.filter(
        MonitoringResult.checked_at >= start_time,
        MonitoringResult.latency.isnot(None),
    ).order_by(MonitoringResult.checked_at.desc()).limit(100).all()

    points = []
    for result in reversed(results):
        points.append({
            "time": result.checked_at.isoformat(),
            "latency": result.latency,
            "device": result.device.name,
        })
    return jsonify(points=points)


@bp.get("/api/dashboard/alerts")
@login_required
def recent_alerts():
    alerts = Alert.query.order_by(Alert.created_at.desc()).limit(8).all()
    return jsonify(alerts=[{
        "id": alert.id,
        "device": alert.device.name,
        "severity": alert.severity,
        "message": alert.message,
        "acknowledged": alert.acknowledged,
        "created_at": alert.created_at.isoformat(),
    } for alert in alerts])


@bp.get("/api/dashboard/activity")
@login_required
def activity():
    logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(8).all()
    return jsonify(activity=[{
        "device": log.device.name if log.device else "System",
        "event_type": log.event_type,
        "message": log.message,
        "created_at": log.created_at.isoformat(),
    } for log in logs])
