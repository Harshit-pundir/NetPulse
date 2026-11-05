from unittest.mock import patch
from types import SimpleNamespace
import threading
from app.models import Device, Alert, MonitoringResult, ActivityLog
from app.services.monitoring_service import classify_latency, monitor_device, start_scheduler, stop_scheduler, should_start_monitoring
from .conftest import csrf_headers, login


def test_login_logout_and_protected_routes(client):
    assert client.get("/").url.path == "/login"
    assert login(client).status_code == 200
    assert client.get("/api/dashboard/summary").status_code == 200
    assert client.post("/logout", headers=csrf_headers(client), follow_redirects=False).status_code == 303


def test_device_crud_and_viewer_permission(client):
    login(client, "viewer")
    response = client.post("/api/devices", json={"name":"Denied", "ip_address":"1.1.1.1", "device_type":"SERVER"}, headers=csrf_headers(client))
    assert response.status_code == 403
    client.post("/logout", headers=csrf_headers(client))
    login(client)
    payload = {"name":"DNS", "ip_address":"1.1.1.1", "device_type":"SERVER"}
    assert client.post("/api/devices", json=payload, headers=csrf_headers(client)).status_code == 201
    assert client.post("/api/devices", json=payload, headers=csrf_headers(client)).status_code == 409
    listing = client.get("/api/devices").json()
    assert listing["total"] == 1
    device_id = listing["devices"][0]["id"]
    updated = {**payload, "name": "DNS Updated"}
    assert client.put(f"/api/devices/{device_id}", json=updated, headers=csrf_headers(client)).json()["name"] == "DNS Updated"
    assert client.delete(f"/api/devices/{device_id}", headers=csrf_headers(client)).status_code == 204


def test_dashboard_alert_acknowledgement_and_pages(client):
    login(client)
    response = client.post("/api/devices", json={"name":"DNS", "ip_address":"8.8.8.8", "device_type":"SERVER"}, headers=csrf_headers(client))
    device_id = response.json()["id"]
    assert client.get("/api/dashboard/summary").status_code == 200
    assert client.get("/api/alerts").status_code == 200
    assert client.get("/api/logs").status_code == 200
    for path in ("/", "/devices", f"/devices/{device_id}", "/alerts", "/logs"):
        assert client.get(path).status_code == 200


def test_status_classification():
    assert classify_latency(None, 100, 200) == "OFFLINE"
    assert classify_latency(101, 100, 200) == "WARNING"
    assert classify_latency(201, 100, 200) == "CRITICAL"
    assert classify_latency(10, 100, 200) == "ONLINE"


def test_monitoring_records_results_and_only_alerts_on_transitions(client, monkeypatch):
    factory = client.app.state.test_session_factory
    monkeypatch.setattr("app.services.monitoring_service.SessionLocal", factory)
    with factory() as session:
        device = Device(name="Router", ip_address="10.0.0.1", device_type="ROUTER", status="ONLINE")
        session.add(device); session.commit(); device_id = device.id
        with patch("app.services.monitoring_service.ping_host", return_value=(False, None, "unreachable")):
            assert monitor_device(device, session, {"LATENCY_WARNING_MS": 100, "LATENCY_CRITICAL_MS": 200}) == "OFFLINE"
            assert monitor_device(device, session, {"LATENCY_WARNING_MS": 100, "LATENCY_CRITICAL_MS": 200}) == "OFFLINE"
        assert session.query(MonitoringResult).filter_by(device_id=device_id).count() == 2
        assert session.query(Alert).filter_by(device_id=device_id, alert_type="DEVICE_DOWN").count() == 1
        with patch("app.services.monitoring_service.ping_host", return_value=(True, 20, None)):
            assert monitor_device(device, session, {"LATENCY_WARNING_MS": 100, "LATENCY_CRITICAL_MS": 200}) == "ONLINE"
        assert session.query(Alert).filter_by(device_id=device_id, alert_type="DEVICE_RECOVERED").count() == 1
        assert session.query(ActivityLog).filter_by(device_id=device_id, event_type="STATUS_CHANGE").count() == 2


def test_fastapi_monitoring_worker_starts_once_and_stops(monkeypatch):
    cycle_finished = threading.Event()
    worker_app = SimpleNamespace(state=SimpleNamespace(config={"START_MONITORING": True, "MONITOR_INTERVAL": 60}))
    def one_cycle(stop_event, _config):
        cycle_finished.set()
    monkeypatch.setattr("app.services.monitoring_service.monitor_all_devices", one_cycle)
    assert should_start_monitoring(worker_app, False)
    assert start_scheduler(worker_app) is True
    assert cycle_finished.wait(2)
    assert start_scheduler(worker_app) is False
    assert stop_scheduler(worker_app) is True


def test_registration(client):
    response = client.post("/register", json={"username":"new-user", "password":"longpassword"}, headers=csrf_headers(client))
    assert response.status_code == 201
    assert client.post("/register", json={"username":"new-user", "password":"longpassword"}, headers=csrf_headers(client)).status_code == 409


def test_swagger_docs_exist(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
