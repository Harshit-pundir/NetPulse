from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from ..models import ActivityLog, Device

bp = Blueprint("logs", __name__)


@bp.route("/logs")
@login_required
def page():
    devices = Device.query.order_by(Device.name).all()
    return render_template("logs.html", devices=devices)


@bp.get("/api/logs")
@login_required
def list_logs():
    query = ActivityLog.query
    device_id = request.args.get("device_id", type=int)
    search_text = request.args.get("search", "").strip()

    if device_id:
        query = query.filter_by(device_id=device_id)
    if search_text:
        query = query.filter(ActivityLog.message.ilike(f"%{search_text}%"))

    page_number = max(1, request.args.get("page", 1, type=int))
    pagination = query.order_by(ActivityLog.created_at.desc()).paginate(page=page_number, per_page=25, error_out=False)
    logs = []
    for log in pagination.items:
        device_name = "System"
        ip_address = "-"
        if log.device:
            device_name = log.device.name
            ip_address = log.device.ip_address

        logs.append({
            "id": log.id,
            "device": device_name,
            "ip": ip_address,
            "event_type": log.event_type,
            "message": log.message,
            "created_at": log.created_at.isoformat(),
        })

    return jsonify(logs=logs, total=pagination.total, pages=pagination.pages)
