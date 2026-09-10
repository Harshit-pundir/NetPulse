from datetime import datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from ..extensions import db
from ..models import ActivityLog, Alert, Device
from .helpers import admin_required

bp = Blueprint("alerts", __name__)


@bp.route("/alerts")
@login_required
def page():
    devices = Device.query.order_by(Device.name).all()
    return render_template("alerts.html", devices=devices)


@bp.get("/api/alerts")
@login_required
def list_alerts():
    query = Alert.query
    severity = request.args.get("severity")
    device_id = request.args.get("device_id", type=int)
    acknowledged = request.args.get("acknowledged")

    if severity:
        query = query.filter_by(severity=severity)
    if device_id:
        query = query.filter_by(device_id=device_id)
    if acknowledged in ("true", "false"):
        query = query.filter_by(acknowledged=acknowledged == "true")

    page_number = max(1, request.args.get("page", 1, type=int))
    pagination = query.order_by(Alert.created_at.desc()).paginate(page=page_number, per_page=20, error_out=False)
    alerts = []
    for alert in pagination.items:
        alerts.append({
            "id": alert.id,
            "device": alert.device.name,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "acknowledged": alert.acknowledged,
            "created_at": alert.created_at.isoformat(),
        })

    return jsonify(alerts=alerts, total=pagination.total, pages=pagination.pages)


@bp.patch("/api/alerts/<int:alert_id>/acknowledge")
@login_required
@admin_required
def acknowledge(alert_id):
    alert = db.get_or_404(Alert, alert_id)
    if not alert.acknowledged:
        alert.acknowledged = True
        alert.acknowledged_at = datetime.utcnow()
        message = f"Alert acknowledged: {alert.message}"
        db.session.add(ActivityLog(device_id=alert.device_id, event_type="ALERT_ACKNOWLEDGED", message=message))
        db.session.commit()

    return jsonify(id=alert.id, acknowledged=True)
