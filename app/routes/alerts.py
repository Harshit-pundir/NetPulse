from datetime import datetime
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from ..extensions import db
from ..models import Alert, Device, ActivityLog
from .helpers import admin_required
bp=Blueprint('alerts',__name__)
@bp.route('/alerts')
@login_required
def page(): return render_template('alerts.html', devices=Device.query.order_by(Device.name).all())
@bp.get('/api/alerts')
@login_required
def list_alerts():
    q=Alert.query; severity=request.args.get('severity'); device_id=request.args.get('device_id',type=int); acknowledged=request.args.get('acknowledged')
    if severity:q=q.filter_by(severity=severity)
    if device_id:q=q.filter_by(device_id=device_id)
    if acknowledged in ('true','false'):q=q.filter_by(acknowledged=acknowledged=='true')
    p=q.order_by(Alert.created_at.desc()).paginate(page=max(1,request.args.get('page',1,type=int)),per_page=20,error_out=False)
    return jsonify(alerts=[{'id':a.id,'device':a.device.name,'alert_type':a.alert_type,'severity':a.severity,'message':a.message,'acknowledged':a.acknowledged,'created_at':a.created_at.isoformat()} for a in p.items],total=p.total,pages=p.pages)
@bp.patch('/api/alerts/<int:alert_id>/acknowledge')
@login_required
@admin_required
def acknowledge(alert_id):
    a=db.get_or_404(Alert,alert_id)
    if not a.acknowledged:
        a.acknowledged=True;a.acknowledged_at=datetime.utcnow();db.session.add(ActivityLog(device_id=a.device_id,event_type='ALERT_ACKNOWLEDGED',message=f'Alert acknowledged: {a.message}'));db.session.commit()
    return jsonify(id=a.id,acknowledged=True)
