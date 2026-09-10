import ipaddress
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import ActivityLog, Device, MonitoringResult
from ..services.uptime_service import uptime_for
from .helpers import admin_required, device_json

bp = Blueprint("devices", __name__)
DEVICE_TYPES = {"ROUTER", "SWITCH", "SERVER", "PC", "ACCESS_POINT", "OTHER"}


def valid_target(value):
    """Accept either an IP address or a simple hostname."""
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return bool(value and all(character.isalnum() or character in ".-" for character in value))


def payload_error(data):
    if not data.get("name", "").strip():
        return "Name is required."
    if not valid_target(data.get("ip_address", "").strip()):
        return "A valid IP address or hostname is required."
    if data.get("device_type") not in DEVICE_TYPES:
        return "A valid device type is required."
    return None


def clean_device_fields(data):
    return {
        "name": data["name"].strip(),
        "ip_address": data["ip_address"].strip(),
        "hostname": data.get("hostname", "").strip() or None,
        "device_type": data["device_type"],
        "location": data.get("location", "").strip() or None,
        "description": data.get("description", "").strip() or None,
    }


@bp.route("/devices")
@login_required
def page():
    return render_template("devices.html", types=sorted(DEVICE_TYPES))


@bp.get("/devices/<int:device_id>")
@login_required
def details(device_id):
    device = db.get_or_404(Device, device_id)
    return render_template("device_details.html", device=device)


@bp.get("/api/devices")
@login_required
def list_devices():
    query = Device.query
    search_text = request.args.get("search", "").strip()
    status = request.args.get("status")

    if search_text:
        query = query.filter(or_(Device.name.ilike(f"%{search_text}%"), Device.ip_address.ilike(f"%{search_text}%")))
    if status:
        query = query.filter_by(status=status)

    page_number = max(1, request.args.get("page", 1, type=int))
    pagination = query.order_by(Device.name).paginate(page=page_number, per_page=15, error_out=False)
    return jsonify(
        devices=[device_json(device) for device in pagination.items],
        page=page_number,
        pages=pagination.pages,
        total=pagination.total,
    )


@bp.post("/api/devices")
@login_required
@admin_required
def create():
    data = request.get_json(silent=True) or request.form
    error = payload_error(data)
    if error:
        return jsonify(error=error), 400

    fields = clean_device_fields(data)
    duplicate = Device.query.filter(or_(Device.name == fields["name"], Device.ip_address == fields["ip_address"])).first()
    if duplicate:
        return jsonify(error="A device with that name or address already exists."), 409

    device = Device(**fields)
    db.session.add(device)
    db.session.flush()
    db.session.add(ActivityLog(device_id=device.id, event_type="DEVICE_ADDED", message=f"{device.name} added."))
    db.session.commit()
    return jsonify(device_json(device)), 201


@bp.route("/api/devices/<int:device_id>", methods=["GET", "PUT", "DELETE"])
@login_required
def device_api(device_id):
    device = db.get_or_404(Device, device_id)
    if request.method == "GET":
        return jsonify(device_json(device))

    if current_user.role != "ADMIN":
        return jsonify(error="Administrator access required"), 403

    if request.method == "DELETE":
        db.session.delete(device)
        db.session.commit()
        return "", 204

    data = request.get_json(silent=True) or {}
    error = payload_error(data)
    if error:
        return jsonify(error=error), 400

    fields = clean_device_fields(data)
    duplicate = Device.query.filter(Device.id != device.id, or_(Device.name == fields["name"], Device.ip_address == fields["ip_address"])).first()
    if duplicate:
        return jsonify(error="A device with that name or address already exists."), 409

    for field_name, value in fields.items():
        setattr(device, field_name, value)
    db.session.commit()
    return jsonify(device_json(device))


@bp.patch("/api/devices/<int:device_id>/monitoring")
@login_required
@admin_required
def toggle(device_id):
    device = db.get_or_404(Device, device_id)
    data = request.get_json(silent=True) or {}
    device.monitoring_enabled = bool(data.get("monitoring_enabled"))

    state = "enabled" if device.monitoring_enabled else "disabled"
    db.session.add(ActivityLog(device_id=device.id, event_type="MONITORING_TOGGLED", message=f"Monitoring {state}."))
    db.session.commit()
    return jsonify(device_json(device))


@bp.get("/api/devices/<int:device_id>/history")
@login_required
def history(device_id):
    db.get_or_404(Device, device_id)
    hours = min(request.args.get("hours", 24, type=int), 168)
    start_time = datetime.utcnow() - timedelta(hours=hours)
    results = MonitoringResult.query.filter_by(device_id=device_id).filter(
        MonitoringResult.checked_at >= start_time
    ).order_by(MonitoringResult.checked_at).limit(500).all()

    return jsonify(history=[{
        "status": result.status,
        "latency": result.latency,
        "checked_at": result.checked_at.isoformat(),
    } for result in results])


@bp.get("/api/devices/<int:device_id>/uptime")
@login_required
def uptime(device_id):
    db.get_or_404(Device, device_id)
    return jsonify(**{str(hours): uptime_for(device_id, hours) for hours in (1, 24, 168)})
