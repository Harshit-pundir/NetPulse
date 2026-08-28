from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from ..models import ActivityLog, Device
bp=Blueprint('logs',__name__)
@bp.route('/logs')
@login_required
def page(): return render_template('logs.html',devices=Device.query.order_by(Device.name).all())
@bp.get('/api/logs')
@login_required
def list_logs():
    q=ActivityLog.query; device_id=request.args.get('device_id',type=int); search=request.args.get('search','')
    if device_id:q=q.filter_by(device_id=device_id)
    if search:q=q.filter(ActivityLog.message.ilike(f'%{search}%'))
    p=q.order_by(ActivityLog.created_at.desc()).paginate(page=max(1,request.args.get('page',1,type=int)),per_page=25,error_out=False)
    return jsonify(logs=[{'id':x.id,'device':x.device.name if x.device else 'System','ip':x.device.ip_address if x.device else '—','event_type':x.event_type,'message':x.message,'created_at':x.created_at.isoformat()} for x in p.items],total=p.total,pages=p.pages)
