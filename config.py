import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    """Settings read by Flask when the application starts."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-this-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'instance' / 'network_monitor.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL", "10"))
    LATENCY_WARNING_MS = float(os.getenv("LATENCY_WARNING_MS", "100"))
    LATENCY_CRITICAL_MS = float(os.getenv("LATENCY_CRITICAL_MS", "200"))
    START_MONITORING = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
