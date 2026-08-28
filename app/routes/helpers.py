from functools import wraps
from flask import jsonify
from flask_login import current_user

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated: return jsonify(error='Authentication required'), 401
        if current_user.role != 'ADMIN': return jsonify(error='Administrator access required'), 403
        return fn(*args, **kwargs)
    return wrapped

def device_json(d):
    return {'id':d.id,'name':d.name,'ip_address':d.ip_address,'hostname':d.hostname,'device_type':d.device_type,'location':d.location,'description':d.description,'monitoring_enabled':d.monitoring_enabled,'status':d.status,'current_latency':d.current_latency,'last_checked_at':d.last_checked_at.isoformat() if d.last_checked_at else None}
