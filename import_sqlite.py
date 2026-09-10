"""Copy old local NetPulse SQLite data into the configured PostgreSQL database.

Run this once only when the old SQLite file contains data you want to keep:
    python import_sqlite.py instance/network_monitor.db
"""

import sqlite3
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.extensions import db
from app.models import ActivityLog, Alert, Device, MonitoringResult, User


def copy_rows(connection, table_name, model, columns):
    """Copy rows by primary key, skipping rows already present in PostgreSQL."""
    rows = connection.execute(f"SELECT {', '.join(columns)} FROM {table_name}").fetchall()
    copied_rows = 0

    for row in rows:
        values = dict(zip(columns, row))
        if db.session.get(model, values["id"]):
            continue
        db.session.add(model(**values))
        copied_rows += 1

    return copied_rows


def reset_postgresql_sequences():
    """Move PostgreSQL ID counters after importing rows with existing IDs."""
    tables = [User, Device, MonitoringResult, Alert, ActivityLog]
    for model in tables:
        table_name = model.__tablename__
        # PostgreSQL does not automatically move a serial sequence after explicit IDs.
        statement = text(
            f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
            f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table_name}"
        )
        db.session.execute(statement)


def import_database(sqlite_path):
    """Create target tables, then copy tables in foreign-key order."""
    source_path = Path(sqlite_path)
    if not source_path.is_file():
        print(f"SQLite file not found: {source_path}")
        return 1

    try:
        app = create_app({"START_MONITORING": False})
        with app.app_context():
            db.create_all()
            source = sqlite3.connect(source_path)
            try:
                counts = {
                    "users": copy_rows(source, "user", User, ["id", "username", "password_hash", "role", "created_at"]),
                    "devices": copy_rows(source, "device", Device, ["id", "name", "ip_address", "hostname", "device_type", "location", "description", "monitoring_enabled", "status", "current_latency", "last_checked_at", "created_at", "updated_at"]),
                    "monitoring results": copy_rows(source, "monitoring_result", MonitoringResult, ["id", "device_id", "status", "latency", "response_time", "checked_at", "error_message"]),
                    "alerts": copy_rows(source, "alert", Alert, ["id", "device_id", "alert_type", "severity", "message", "acknowledged", "created_at", "acknowledged_at"]),
                    "activity logs": copy_rows(source, "activity_log", ActivityLog, ["id", "device_id", "event_type", "message", "created_at"]),
                }
            finally:
                source.close()

            db.session.commit()
            reset_postgresql_sequences()
            db.session.commit()
    except (RuntimeError, SQLAlchemyError, sqlite3.Error) as error:
        print(f"Import failed: {error}")
        return 1

    summary = ", ".join(f"{name}={count}" for name, count in counts.items())
    print(f"Import complete: {summary}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python import_sqlite.py PATH_TO_OLD_DATABASE")
        raise SystemExit(1)
    raise SystemExit(import_database(sys.argv[1]))
