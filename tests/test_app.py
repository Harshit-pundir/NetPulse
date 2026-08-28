from unittest.mock import patch
from app.extensions import db
from app.models import Device, Alert
from app.services.monitoring_service import classify_latency, monitor_device, should_start_monitoring, start_scheduler
from app.services.uptime_service import uptime_for
from .conftest import login

def test_login_logout_and_protection(client):
    assert client.get('/').status_code in (302,401); assert login(client).status_code==200; assert client.post('/logout').status_code==302
def test_role_restriction(viewer):
    assert viewer.post('/api/devices',json={'name':'A','ip_address':'1.1.1.1','device_type':'SERVER'}).status_code==403
def test_device_crud_validation(admin):
    data={'name':'DNS','ip_address':'1.1.1.1','device_type':'SERVER'}; assert admin.post('/api/devices',json=data).status_code==201; assert admin.post('/api/devices',json=data).status_code==409; assert admin.post('/api/devices',json={'name':'x','ip_address':'no bad!','device_type':'PC'}).status_code==400
def test_monitoring_alerts_and_uptime(app):
    with app.app_context():
        d=Device(name='Test',ip_address='10.0.0.1',device_type='SERVER',status='ONLINE');db.session.add(d);db.session.commit()
        with patch('app.services.monitoring_service.ping_host',return_value=(False,None,'down')): assert monitor_device(d)=='OFFLINE'
        assert Alert.query.filter_by(alert_type='DEVICE_DOWN').count()==1
        with patch('app.services.monitoring_service.ping_host',return_value=(False,None,'down')): monitor_device(d)
        assert Alert.query.filter_by(alert_type='DEVICE_DOWN').count()==1
        with patch('app.services.monitoring_service.ping_host',return_value=(True,20,None)): assert monitor_device(d)=='ONLINE'
        assert Alert.query.filter_by(alert_type='DEVICE_RECOVERED').count()==1; assert uptime_for(d.id,1)>0
def test_classification(): assert classify_latency(None,100,200)=='OFFLINE' and classify_latency(101,100,200)=='WARNING' and classify_latency(10,100,200)=='ONLINE'
def test_reloader_parent_does_not_start_monitoring(app, monkeypatch):
    app.config['TESTING'] = False
    monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
    assert not should_start_monitoring(app, True)
    monkeypatch.setenv('WERKZEUG_RUN_MAIN', 'true')
    assert should_start_monitoring(app, True)
def test_scheduler_starts_once_per_app(app, monkeypatch):
    app.testing = False
    started = []
    class Thread:
        def __init__(self, **kwargs): started.append(kwargs)
        def start(self): pass
    monkeypatch.setattr('app.services.monitoring_service.threading.Thread', Thread)
    assert start_scheduler(app) is True
    assert start_scheduler(app) is False
    assert len(started) == 1
def test_api_and_acknowledge(admin,app):
    with app.app_context():
        d=Device(name='X',ip_address='8.8.8.8',device_type='SERVER');db.session.add(d);db.session.flush();a=Alert(device_id=d.id,alert_type='DEVICE_DOWN',severity='CRITICAL',message='down');db.session.add(a);db.session.commit();aid=a.id
    assert admin.get('/api/dashboard/summary').status_code==200; assert admin.patch(f'/api/alerts/{aid}/acknowledge').status_code==200
