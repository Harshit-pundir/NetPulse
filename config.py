import os


class Config:
    """Settings read by Flask when the application starts."""

    SECRET_KEY = os.getenv("SECRET_KEY")
    # Supabase provides this PostgreSQL URL. It is intentionally not hardcoded.
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # SQLAlchemy owns the connection pool. pre_ping replaces broken connections.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 300}
    MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL", "10"))
    LATENCY_WARNING_MS = float(os.getenv("LATENCY_WARNING_MS", "100"))
    LATENCY_CRITICAL_MS = float(os.getenv("LATENCY_CRITICAL_MS", "200"))
    START_MONITORING = os.getenv("START_MONITORING", "true").lower() not in {"0", "false", "no"}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
