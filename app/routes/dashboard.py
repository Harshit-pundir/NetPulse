from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify
from flask_login import login_required
from sqlalchemy import func
from ..models import Device, Alert, ActivityLog, MonitoringResult
from .helpers import device_json
bp=Blueprint('dashboard',__name__)
@bp.route('/')
@login_required
def index(): return render_template('dashboard.html')
@bp.get('/api/dashboard/summary')
@login_required
def summary():
    devices=Device.query.all(); counts={s:sum(d.status==s for d in devices) for s in ('ONLINE','OFFLINE','WARNING','UNKNOWN')}
    values=[d.current_latency for d in devices if d.current_latency is not None]
    return jsonify(total=len(devices), online=counts['ONLINE'],offline=counts['OFFLINE'],warning=counts['WARNING'],unknown=counts['UNKNOWN'],active_alerts=Alert.query.filter_by(acknowledged=False).count(),average_latency=round(sum(values)/len(values),1) if values else None,devices=[device_json(d) for d in devices])
@bp.get('/api/dashboard/latency')
@login_required
def latency():
    since=datetime.utcnow()-timedelta(hours=24)
    rows=dbrows=MonitoringResult.query.filter(MonitoringResult.checked_at>=since,MonitoringResult.latency.isnot(None)).order_by(MonitoringResult.checked_at.desc()).limit(100).all()
    return jsonify(points=[{'time':r.checked_at.isoformat(),'latency':r.latency,'device':r.device.name} for r in reversed(rows)])
@bp.get('/api/dashboard/alerts')
@login_required
def recent_alerts():
    alerts=Alert.query.order_by(Alert.created_at.desc()).limit(8).all()
    return jsonify(alerts=[{'id':a.id,'device':a.device.name,'severity':a.severity,'message':a.message,'acknowledged':a.acknowledged,'created_at':a.created_at.isoformat()} for a in alerts])
@bp.get('/api/dashboard/activity')
@login_required
def activity():
    logs=ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(8).all()
    return jsonify(activity=[{'device':a.device.name if a.device else 'System','event_type':a.event_type,'message':a.message,'created_at':a.created_at.isoformat()} for a in logs])
