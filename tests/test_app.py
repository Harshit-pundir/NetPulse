from unittest.mock import patch

from app.extensions import db
from app.models import ActivityLog, Alert, Device, MonitoringResult, User
from app.services.monitoring_service import classify_latency, monitor_device, should_start_monitoring, start_scheduler
from app.services.uptime_service import uptime_for
from .conftest import login


def test_login_logout_and_protection(client):
    assert client.get("/").status_code in (302, 401)
    assert login(client).status_code == 200
    assert client.post("/logout").status_code == 302


def test_viewer_cannot_create_device(viewer):
    response = viewer.post("/api/devices", json={
        "name": "A",
        "ip_address": "1.1.1.1",
        "device_type": "SERVER",
    })
    assert response.status_code == 403


def test_device_crud_validation(admin):
    device = {"name": "DNS", "ip_address": "1.1.1.1", "device_type": "SERVER"}

    assert admin.post("/api/devices", json=device).status_code == 201
    assert admin.post("/api/devices", json=device).status_code == 409

    invalid_device = {"name": "x", "ip_address": "no bad!", "device_type": "PC"}
    assert admin.post("/api/devices", json=invalid_device).status_code == 400


def test_monitoring_alerts_and_uptime(app):
    with app.app_context():
        device = Device(name="Test", ip_address="10.0.0.1", device_type="SERVER", status="ONLINE")
        db.session.add(device)
        db.session.commit()

        with patch("app.services.monitoring_service.ping_host", return_value=(False, None, "down")):
            assert monitor_device(device) == "OFFLINE"
        assert Alert.query.filter_by(alert_type="DEVICE_DOWN").count() == 1

        # The same outage should not create a duplicate active alert.
        with patch("app.services.monitoring_service.ping_host", return_value=(False, None, "down")):
            monitor_device(device)
        assert Alert.query.filter_by(alert_type="DEVICE_DOWN").count() == 1

        with patch("app.services.monitoring_service.ping_host", return_value=(True, 20, None)):
            assert monitor_device(device) == "ONLINE"
        assert Alert.query.filter_by(alert_type="DEVICE_RECOVERED").count() == 1
        assert uptime_for(device.id, 1) > 0


def test_status_classification():
    assert classify_latency(None, 100, 200) == "OFFLINE"
    assert classify_latency(101, 100, 200) == "WARNING"
    assert classify_latency(10, 100, 200) == "ONLINE"


def test_postgresql_table_names_and_indexes():
    assert User.__tablename__ == "users"
    assert Device.__tablename__ == "devices"
    assert MonitoringResult.__tablename__ == "monitoring_results"
    assert Alert.__tablename__ == "alerts"
    assert ActivityLog.__tablename__ == "activity_logs"
    assert "ix_monitoring_results_device_checked_at" in {index.name for index in MonitoringResult.__table__.indexes}


def test_reloader_parent_does_not_start_monitoring(app, monkeypatch):
    app.config["TESTING"] = False
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    assert not should_start_monitoring(app, True)

    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    assert should_start_monitoring(app, True)


def test_scheduler_starts_once_per_app(app, monkeypatch):
    app.testing = False
    started_threads = []

    class Thread:
        def __init__(self, **kwargs):
            started_threads.append(kwargs)

        def start(self):
            pass

    monkeypatch.setattr("app.services.monitoring_service.threading.Thread", Thread)
    assert start_scheduler(app) is True
    assert start_scheduler(app) is False
    assert len(started_threads) == 1


def test_dashboard_api_and_acknowledge_alert(admin, app):
    with app.app_context():
        device = Device(name="X", ip_address="8.8.8.8", device_type="SERVER")
        db.session.add(device)
        db.session.flush()
        alert = Alert(device_id=device.id, alert_type="DEVICE_DOWN", severity="CRITICAL", message="down")
        db.session.add(alert)
        db.session.commit()
        alert_id = alert.id

    assert admin.get("/api/dashboard/summary").status_code == 200
    assert admin.patch(f"/api/alerts/{alert_id}/acknowledge").status_code == 200
