from datetime import datetime

from flask_login import UserMixin

from .extensions import db


class User(UserMixin, db.Model):
    """A person who can sign in to NetPulse."""

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="VIEWER")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Device(db.Model):
    """A network device that NetPulse can monitor."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    ip_address = db.Column(db.String(255), unique=True, nullable=False, index=True)
    hostname = db.Column(db.String(255))
    device_type = db.Column(db.String(30), nullable=False, default="OTHER")
    location = db.Column(db.String(120))
    description = db.Column(db.Text)
    monitoring_enabled = db.Column(db.Boolean, nullable=False, default=True)
    status = db.Column(db.String(16), nullable=False, default="UNKNOWN", index=True)
    current_latency = db.Column(db.Float)
    last_checked_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    results = db.relationship("MonitoringResult", backref="device", lazy="dynamic", cascade="all, delete-orphan")
    alerts = db.relationship("Alert", backref="device", lazy="dynamic", cascade="all, delete-orphan")
    activity_logs = db.relationship("ActivityLog", backref="device", lazy="dynamic", cascade="all, delete-orphan")


class MonitoringResult(db.Model):
    """One reachability check for a device."""

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("device.id"), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, index=True)
    latency = db.Column(db.Float)
    response_time = db.Column(db.Float)
    checked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    error_message = db.Column(db.String(500))


class Alert(db.Model):
    """A device condition that may need a user's attention."""

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("device.id"), nullable=False, index=True)
    alert_type = db.Column(db.String(30), nullable=False, index=True)
    severity = db.Column(db.String(16), nullable=False, index=True)
    message = db.Column(db.String(500), nullable=False)
    acknowledged = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    acknowledged_at = db.Column(db.DateTime)


class ActivityLog(db.Model):
    """A simple audit trail for device and alert events."""

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("device.id"), nullable=True, index=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)
    message = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
