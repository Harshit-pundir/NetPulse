from functools import wraps

from flask import jsonify
from flask_login import current_user


def admin_required(route_function):
    """Allow this route only for signed-in administrators."""
    @wraps(route_function)
    def decorated_route(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify(error="Authentication required"), 401
        if current_user.role != "ADMIN":
            return jsonify(error="Administrator access required"), 403
        return route_function(*args, **kwargs)

    return decorated_route


def device_json(device):
    """Return the device fields used by the browser APIs."""
    last_checked = None
    if device.last_checked_at:
        last_checked = device.last_checked_at.isoformat()

    return {
        "id": device.id,
        "name": device.name,
        "ip_address": device.ip_address,
        "hostname": device.hostname,
        "device_type": device.device_type,
        "location": device.location,
        "description": device.description,
        "monitoring_enabled": device.monitoring_enabled,
        "status": device.status,
        "current_latency": device.current_latency,
        "last_checked_at": last_checked,
    }
