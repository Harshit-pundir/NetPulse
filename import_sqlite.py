"""Copy legacy Flask SQLite data into the configured PostgreSQL database."""
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import text
from app.database import SessionLocal, engine
from app.models import ActivityLog, Alert, Device, MonitoringResult, User


def copy_rows(source, session, old_table, model, columns):
    rows = source.execute(f"SELECT {', '.join(columns)} FROM {old_table}").fetchall()
    copied = 0
    for row in rows:
        values = dict(zip(columns, row))
        if session.get(model, values["id"]): continue
        session.add(model(**values)); copied += 1
    session.flush()
    return copied


def import_database(path):
    source_path = Path(path)
    if not source_path.is_file():
        print(f"SQLite file not found: {source_path}"); return 1
    try:
        # The target Supabase schema must already exist; importing data never makes it.
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        with sqlite3.connect(source_path) as source, SessionLocal() as session:
            counts = {
                "users": copy_rows(source, session, "user", User, ["id", "username", "password_hash", "role", "created_at"]),
                "devices": copy_rows(source, session, "device", Device, ["id", "name", "ip_address", "hostname", "device_type", "location", "description", "monitoring_enabled", "status", "current_latency", "last_checked_at", "created_at", "updated_at"]),
                "monitoring results": copy_rows(source, session, "monitoring_result", MonitoringResult, ["id", "device_id", "status", "latency", "response_time", "checked_at", "error_message"]),
                "alerts": copy_rows(source, session, "alert", Alert, ["id", "device_id", "alert_type", "severity", "message", "acknowledged", "created_at", "acknowledged_at"]),
                "activity logs": copy_rows(source, session, "activity_log", ActivityLog, ["id", "device_id", "event_type", "message", "created_at"]),
            }
            session.commit()
            for model in (User, Device, MonitoringResult, Alert, ActivityLog):
                table = model.__tablename__
                session.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table}"))
            session.commit()
    except Exception as error:
        print(f"Import failed: {error}"); return 1
    print("Import complete: " + ", ".join(f"{name}={count}" for name, count in counts.items()))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python import_sqlite.py PATH_TO_OLD_DATABASE"); raise SystemExit(1)
    raise SystemExit(import_database(sys.argv[1]))
