import ipaddress
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_
from ..extensions import db
from ..models import Device, MonitoringResult, ActivityLog
from .helpers import admin_required, device_json
from ..services.uptime_service import uptime_for
bp=Blueprint('devices',__name__)
TYPES={'ROUTER','SWITCH','SERVER','PC','ACCESS_POINT','OTHER'}
def valid_target(value):
    try: ipaddress.ip_address(value); return True
    except ValueError: return bool(value and all(c.isalnum() or c in '.-' for c in value))
def payload_errors(data):
    if not data.get('name','').strip(): return 'Name is required.'
    if not valid_target(data.get('ip_address','').strip()): return 'A valid IP address or hostname is required.'
    if data.get('device_type') not in TYPES: return 'A valid device type is required.'
@bp.route('/devices')
@login_required
def page(): return render_template('devices.html', types=sorted(TYPES))
@bp.get('/devices/<int:device_id>')
@login_required
def details(device_id):
    device=db.get_or_404(Device,device_id); return render_template('device_details.html',device=device)
@bp.get('/api/devices')
@login_required
def list_devices():
    q=Device.query
    search=request.args.get('search','').strip()
    if search: q=q.filter(or_(Device.name.ilike(f'%{search}%'),Device.ip_address.ilike(f'%{search}%')))
    status=request.args.get('status')
    if status: q=q.filter_by(status=status)
    page=max(1,request.args.get('page',1,type=int)); pagination=q.order_by(Device.name).paginate(page=page,per_page=15,error_out=False)
    return jsonify(devices=[device_json(d) for d in pagination.items],page=page,pages=pagination.pages,total=pagination.total)
@bp.post('/api/devices')
@login_required
@admin_required
def create():
    data=request.get_json(silent=True) or request.form; error=payload_errors(data)
    if error:return jsonify(error=error),400
    if Device.query.filter(or_(Device.name==data['name'].strip(),Device.ip_address==data['ip_address'].strip())).first(): return jsonify(error='A device with that name or address already exists.'),409
    d=Device(name=data['name'].strip(),ip_address=data['ip_address'].strip(),hostname=data.get('hostname','').strip() or None,device_type=data['device_type'],location=data.get('location','').strip() or None,description=data.get('description','').strip() or None)
    db.session.add(d);db.session.flush();db.session.add(ActivityLog(device_id=d.id,event_type='DEVICE_ADDED',message=f'{d.name} added.'));db.session.commit();return jsonify(device_json(d)),201
@bp.route('/api/devices/<int:device_id>',methods=['GET','PUT','DELETE'])
@login_required
def device_api(device_id):
    d=db.get_or_404(Device,device_id)
    if request.method=='GET':return jsonify(device_json(d))
    if request.method=='DELETE':
        if current_user.role!='ADMIN':return jsonify(error='Administrator access required'),403
        db.session.delete(d);db.session.commit();return '',204
    if current_user.role!='ADMIN':return jsonify(error='Administrator access required'),403
    data=request.get_json(silent=True) or {}; error=payload_errors(data)
    if error:return jsonify(error=error),400
    duplicate=Device.query.filter(Device.id!=d.id,or_(Device.name==data['name'].strip(),Device.ip_address==data['ip_address'].strip())).first()
    if duplicate:return jsonify(error='A device with that name or address already exists.'),409
    for f in ('name','ip_address','hostname','device_type','location','description'):
        if f in data:setattr(d,f,data[f].strip() if isinstance(data[f],str) else data[f])
    db.session.commit();return jsonify(device_json(d))
@bp.patch('/api/devices/<int:device_id>/monitoring')
@login_required
@admin_required
def toggle(device_id):
    d=db.get_or_404(Device,device_id);d.monitoring_enabled=bool((request.get_json() or {}).get('monitoring_enabled'))
    db.session.add(ActivityLog(device_id=d.id,event_type='MONITORING_TOGGLED',message=f'Monitoring {"enabled" if d.monitoring_enabled else "disabled"}.'));db.session.commit();return jsonify(device_json(d))
@bp.get('/api/devices/<int:device_id>/history')
@login_required
def history(device_id):
    db.get_or_404(Device,device_id); hours=min(request.args.get('hours',24,type=int),168);since=datetime.utcnow()-timedelta(hours=hours)
    rows=MonitoringResult.query.filter_by(device_id=device_id).filter(MonitoringResult.checked_at>=since).order_by(MonitoringResult.checked_at).limit(500).all()
    return jsonify(history=[{'status':r.status,'latency':r.latency,'checked_at':r.checked_at.isoformat()} for r in rows])
@bp.get('/api/devices/<int:device_id>/uptime')
@login_required
def uptime(device_id):
    db.get_or_404(Device,device_id);return jsonify(**{str(h):uptime_for(device_id,h) for h in (1,24,168)})
