import threading
from unittest.mock import patch

from app.extensions import db
from app.models import ActivityLog, Alert, Device, MonitoringResult, User
from app.services.monitoring_service import (
    classify_latency,
    monitor_all_devices,
    monitor_device,
    should_start_monitoring,
    start_scheduler,
    stop_scheduler,
)
from app.services.uptime_service import uptime_for
from .conftest import csrf_headers, login


def test_login_logout_and_protection(client):
    assert client.get("/").status_code in (302, 401)
    assert login(client).status_code == 200
    assert client.post("/logout", data={"csrf_token": csrf_headers(client)["X-CSRF-Token"]}).status_code == 302


def test_viewer_cannot_create_device(viewer):
    response = viewer.post("/api/devices", json={
        "name": "A",
        "ip_address": "1.1.1.1",
        "device_type": "SERVER",
    }, headers=csrf_headers(viewer))
    assert response.status_code == 403


def test_device_crud_validation(admin):
    device = {"name": "DNS", "ip_address": "1.1.1.1", "device_type": "SERVER"}

    assert admin.post("/api/devices", json=device, headers=csrf_headers(admin)).status_code == 201
    assert admin.post("/api/devices", json=device, headers=csrf_headers(admin)).status_code == 409

    invalid_device = {"name": "x", "ip_address": "no bad!", "device_type": "PC"}
    assert admin.post("/api/devices", json=invalid_device, headers=csrf_headers(admin)).status_code == 400


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
    assert classify_latency(201, 100, 200) == "CRITICAL"
    assert classify_latency(10, 100, 200) == "ONLINE"


def test_monitor_error_does_not_mark_device_offline(app):
    with app.app_context():
        device = Device(name="Ping tool unavailable", ip_address="example.test", device_type="SERVER", status="ONLINE")
        db.session.add(device)
        db.session.commit()

        with patch("app.services.monitoring_service.ping_host", return_value=(False, None, "MONITOR_ERROR: ping executable missing")):
            assert monitor_device(device) == "MONITOR_ERROR"

        assert device.status == "ONLINE"
        assert MonitoringResult.query.one().status == "MONITOR_ERROR"


def test_critical_latency_alert_escalates_and_resolves(app):
    with app.app_context():
        device = Device(name="Latency device", ip_address="example.test", device_type="SERVER")
        db.session.add(device)
        db.session.commit()

        with patch("app.services.monitoring_service.ping_host", return_value=(True, 150, None)):
            assert monitor_device(device) == "WARNING"
        alert = Alert.query.filter_by(alert_type="HIGH_LATENCY").one()
        assert alert.severity == "WARNING"

        with patch("app.services.monitoring_service.ping_host", return_value=(True, 250, None)):
            assert monitor_device(device) == "CRITICAL"
        assert alert.severity == "CRITICAL"
        assert alert.acknowledged is False

        with patch("app.services.monitoring_service.ping_host", return_value=(True, 50, None)):
            assert monitor_device(device) == "ONLINE"
        assert alert.acknowledged is True
        assert alert.acknowledged_at is not None


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


def test_scheduler_stops_cleanly_and_stop_is_idempotent(app, monkeypatch):
    app.config["MONITOR_INTERVAL"] = 60
    cycle_started = threading.Event()

    def monitor_cycle(stop_event):
        cycle_started.set()

    monkeypatch.setattr("app.services.monitoring_service.monitor_all_devices", monitor_cycle)
    assert start_scheduler(app) is True
    assert cycle_started.wait(2)
    assert stop_scheduler(app) is True
    assert stop_scheduler(app) is True
    assert start_scheduler(app) is False


def test_shutdown_signal_prevents_starting_the_next_device_check(app, monkeypatch):
    with app.app_context():
        db.session.add_all([
            Device(name="First", ip_address="first.test", device_type="SERVER"),
            Device(name="Second", ip_address="second.test", device_type="SERVER"),
        ])
        db.session.commit()
        stop_event = threading.Event()
        started = []

        def check_device(device):
            started.append(device.name)
            stop_event.set()

        monkeypatch.setattr("app.services.monitoring_service.monitor_device", check_device)
        monitor_all_devices(stop_event)
        assert started == ["First"]


def test_stop_scheduler_handles_only_keyboard_interrupt_from_join(app):
    class InterruptedThread:
        def join(self, _timeout):
            raise KeyboardInterrupt()

        def is_alive(self):
            return True

    app.extensions["netpulse_monitoring_stop_event"] = threading.Event()
    app.extensions["netpulse_monitoring_thread"] = InterruptedThread()
    app.extensions["netpulse_monitoring_worker_started"] = True
    assert stop_scheduler(app) is False
    assert app.extensions["netpulse_monitoring_stop_event"].is_set()


def test_stop_scheduler_does_not_hide_other_join_errors(app):
    import pytest

    class FailedThread:
        def join(self, _timeout):
            raise RuntimeError("unexpected join failure")

    app.extensions["netpulse_monitoring_stop_event"] = threading.Event()
    app.extensions["netpulse_monitoring_thread"] = FailedThread()
    app.extensions["netpulse_monitoring_worker_started"] = True
    with pytest.raises(RuntimeError, match="unexpected join failure"):
        stop_scheduler(app)


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
    assert admin.patch(f"/api/alerts/{alert_id}/acknowledge", headers=csrf_headers(admin)).status_code == 200


def test_authenticated_pages_render(admin, app):
    with app.app_context():
        device = Device(name="Page check", ip_address="localhost", device_type="SERVER")
        db.session.add(device)
        db.session.commit()
        device_id = device.id

    for path in ("/", "/devices", f"/devices/{device_id}", "/alerts", "/logs"):
        assert admin.get(path).status_code == 200
