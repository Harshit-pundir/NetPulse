import threading
from types import SimpleNamespace
from unittest.mock import patch

from app.main import app
from app.services.monitoring_service import classify_latency, monitor_device, should_start_monitoring, start_scheduler, stop_scheduler
from app.services.uptime_service import uptime_for
from .conftest import csrf_headers, login


def test_login_logout_and_protected_routes(client):
    assert client.get("/").url.path == "/login"
    assert login(client).status_code == 200
    assert client.get("/api/dashboard/summary").status_code == 200
    assert client.post("/logout", headers=csrf_headers(client), follow_redirects=False).status_code == 303


def test_device_crud_and_viewer_permission(client):
    login(client, "viewer")
    forbidden = client.post("/api/devices", json={"name": "Denied", "ip_address": "1.1.1.1", "device_type": "SERVER"}, headers=csrf_headers(client))
    assert forbidden.status_code == 403
    client.post("/logout", headers=csrf_headers(client))
    login(client)
    payload = {"name": "DNS", "ip_address": "1.1.1.1", "device_type": "SERVER"}
    assert client.post("/api/devices", json=payload, headers=csrf_headers(client)).status_code == 201
    assert client.post("/api/devices", json=payload, headers=csrf_headers(client)).status_code == 409
    listing = client.get("/api/devices").json()
    assert listing["total"] == 1
    device_id = listing["devices"][0]["id"]
    assert client.put(f"/api/devices/{device_id}", json={**payload, "name": "DNS updated"}, headers=csrf_headers(client)).json()["name"] == "DNS updated"
    assert client.delete(f"/api/devices/{device_id}", headers=csrf_headers(client)).status_code == 204


def test_dashboard_alert_ack_logs_and_pages(client):
    login(client)
    device = client.post("/api/devices", json={"name": "DNS", "ip_address": "8.8.8.8", "device_type": "SERVER"}, headers=csrf_headers(client)).json()
    fake = app.state.test_supabase
    alert = fake.table("alerts").insert({"device_id": device["id"], "alert_type": "DEVICE_DOWN", "severity": "CRITICAL", "message": "down"}).execute().data[0]
    assert client.get("/api/dashboard/summary").json()["total"] == 1
    assert client.get("/api/alerts").json()["total"] == 1
    assert client.patch(f"/api/alerts/{alert['id']}/acknowledge", headers=csrf_headers(client)).json()["acknowledged"] is True
    assert client.get("/api/logs").status_code == 200
    for path in ("/", "/devices", f"/devices/{device['id']}", "/alerts", "/logs"):
        assert client.get(path).status_code == 200


def test_status_classification():
    assert classify_latency(None, 100, 200) == "OFFLINE"
    assert classify_latency(101, 100, 200) == "WARNING"
    assert classify_latency(201, 100, 200) == "CRITICAL"
    assert classify_latency(10, 100, 200) == "ONLINE"


def test_monitoring_saves_results_and_avoids_duplicate_alerts(client, monkeypatch):
    fake = app.state.test_supabase
    device = fake.table("devices").insert({"name": "Router", "ip_address": "10.0.0.1", "device_type": "ROUTER", "status": "ONLINE"}).execute().data[0]
    monkeypatch.setattr("app.services.monitoring_service.supabase", fake)
    with patch("app.services.monitoring_service.ping_host", return_value=(False, None, "unreachable")):
        assert monitor_device(device) == "OFFLINE"
        assert monitor_device(device) == "OFFLINE"
    assert len(fake.tables["monitoring_results"]) == 2
    assert len([row for row in fake.tables["alerts"] if row["alert_type"] == "DEVICE_DOWN"]) == 1
    with patch("app.services.monitoring_service.ping_host", return_value=(True, 20, None)):
        assert monitor_device(device) == "ONLINE"
    assert len([row for row in fake.tables["alerts"] if row["alert_type"] == "DEVICE_RECOVERED"]) == 1
    assert round(uptime_for(device["id"], 24), 2) == 33.33


def test_high_latency_alert_escalates_and_resolves(client, monkeypatch):
    fake = app.state.test_supabase
    device = fake.table("devices").insert({"name": "Slow server", "ip_address": "10.0.0.2", "device_type": "SERVER", "status": "ONLINE"}).execute().data[0]
    monkeypatch.setattr("app.services.monitoring_service.supabase", fake)
    with patch("app.services.monitoring_service.ping_host", return_value=(True, 150, None)):
        assert monitor_device(device, {"LATENCY_WARNING_MS": 100, "LATENCY_CRITICAL_MS": 200}) == "WARNING"
    with patch("app.services.monitoring_service.ping_host", return_value=(True, 250, None)):
        assert monitor_device(device, {"LATENCY_WARNING_MS": 100, "LATENCY_CRITICAL_MS": 200}) == "CRITICAL"
    alerts = [row for row in fake.tables["alerts"] if row["alert_type"] == "HIGH_LATENCY"]
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "CRITICAL"
    with patch("app.services.monitoring_service.ping_host", return_value=(True, 50, None)):
        assert monitor_device(device, {"LATENCY_WARNING_MS": 100, "LATENCY_CRITICAL_MS": 200}) == "ONLINE"
    assert alerts[0]["acknowledged"] is True


def test_fastapi_monitoring_worker_starts_once_and_stops(monkeypatch):
    finished = threading.Event()
    worker_app = SimpleNamespace(state=SimpleNamespace(config={"START_MONITORING": True, "MONITOR_INTERVAL": 60}))
    monkeypatch.setattr("app.services.monitoring_service.monitor_all_devices", lambda *_args: finished.set())
    assert should_start_monitoring(worker_app)
    assert start_scheduler(worker_app) is True
    assert finished.wait(2)
    assert start_scheduler(worker_app) is False
    assert stop_scheduler(worker_app) is True


def test_registration_and_swagger_docs(client):
    result = client.post("/register", json={"username": "new-user", "password": "longpassword"}, headers=csrf_headers(client))
    assert result.status_code == 201
    assert client.post("/register", json={"username": "new-user", "password": "longpassword"}, headers=csrf_headers(client)).status_code == 409
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
