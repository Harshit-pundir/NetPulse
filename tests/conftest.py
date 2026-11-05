"""Route tests use an in-memory fake; they never call a real Supabase project."""
import os
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from werkzeug.security import generate_password_hash

# The central client checks these at import. These values are test-only and are
# replaced with a fake client before any route is called.
os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_KEY"] = "test-only-key"
os.environ["SECRET_KEY"] = "test-only-secret"

from app.main import app
from app import database
from app import main
from app.services import alert_service, monitoring_service, uptime_service


class FakeQuery:
    def __init__(self, client, table):
        self.client, self.table_name = client, table
        self.action, self.payload = "select", None
        self.filters, self.or_filters = [], []
        self.ordering, self.limit_value, self.range_value = None, None, None
        self.exact_count = False

    def select(self, _columns="*", count=None):
        self.action, self.exact_count = "select", count == "exact"
        return self

    def insert(self, payload): self.action, self.payload = "insert", payload; return self
    def update(self, payload): self.action, self.payload = "update", payload; return self
    def delete(self): self.action = "delete"; return self
    def eq(self, field, value): self.filters.append(("eq", field, value)); return self
    def neq(self, field, value): self.filters.append(("neq", field, value)); return self
    def gte(self, field, value): self.filters.append(("gte", field, value)); return self
    def ilike(self, field, value): self.filters.append(("ilike", field, value)); return self
    def limit(self, value): self.limit_value = value; return self
    def range(self, start, end): self.range_value = (start, end); return self
    def order(self, field, desc=False): self.ordering = (field, desc); return self

    def or_(self, expression):
        for item in expression.split(","):
            field, operation, value = item.split(".", 2)
            self.or_filters.append((operation, field, value.strip("%")))
        return self

    def _matches(self, row, operation, field, value):
        actual = row.get(field)
        if operation == "eq": return actual == value
        if operation == "neq": return actual != value
        if operation == "gte": return str(actual or "") >= str(value)
        if operation == "ilike": return str(value).strip("%").lower() in str(actual or "").lower()
        return False

    def _selected(self):
        rows = list(self.client.tables.setdefault(self.table_name, []))
        rows = [row for row in rows if all(self._matches(row, op, field, value) for op, field, value in self.filters)]
        if self.or_filters:
            rows = [row for row in rows if any(self._matches(row, op, field, value) for op, field, value in self.or_filters)]
        return rows

    def execute(self):
        table = self.client.tables.setdefault(self.table_name, [])
        if self.action == "insert":
            inserted = []
            values = self.payload if isinstance(self.payload, list) else [self.payload]
            now = datetime.now(timezone.utc).isoformat()
            for value in values:
                row = dict(value)
                row.setdefault("id", max((item["id"] for item in table), default=0) + 1)
                row.setdefault("created_at", now)
                if self.table_name == "devices":
                    row.setdefault("status", "UNKNOWN"); row.setdefault("monitoring_enabled", True)
                    row.setdefault("current_latency", None); row.setdefault("last_checked_at", None)
                    row.setdefault("hostname", None); row.setdefault("location", None); row.setdefault("description", None)
                if self.table_name == "alerts": row.setdefault("acknowledged", False)
                table.append(row); inserted.append(dict(row))
            return SimpleNamespace(data=inserted, count=len(inserted))

        rows = self._selected()
        if self.action == "update":
            for row in rows: row.update(self.payload)
            return SimpleNamespace(data=[dict(row) for row in rows], count=len(rows))
        if self.action == "delete":
            ids = {id(row) for row in rows}
            self.client.tables[self.table_name] = [row for row in table if id(row) not in ids]
            return SimpleNamespace(data=[dict(row) for row in rows], count=len(rows))

        total = len(rows)
        if self.ordering:
            field, desc = self.ordering
            rows.sort(key=lambda row: row.get(field) or "", reverse=desc)
        if self.range_value:
            start, end = self.range_value; rows = rows[start:end + 1]
        if self.limit_value is not None:
            rows = rows[:self.limit_value]
        return SimpleNamespace(data=[dict(row) for row in rows], count=total if self.exact_count else None)


class FakeSupabase:
    def __init__(self):
        self.tables = {"users": [
            {"id": 1, "username": "admin", "password_hash": generate_password_hash("pass"), "role": "ADMIN"},
            {"id": 2, "username": "viewer", "password_hash": generate_password_hash("pass"), "role": "VIEWER"},
        ]}

    def table(self, name): return FakeQuery(self, name)


@pytest.fixture
def client(monkeypatch):
    fake = FakeSupabase()
    app.state.test_supabase = fake
    for module in (database, main, alert_service, monitoring_service, uptime_service):
        monkeypatch.setattr(module, "supabase", fake)
    app.state.config["TESTING"] = True
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.state.config["TESTING"] = False
    app.dependency_overrides.clear()


def csrf_token(client, path="/login"):
    html = client.get(path, follow_redirects=True).text
    return re.search(r'name="csrf-token" content="([^"]+)', html).group(1)


def login(client, username="admin"):
    token = csrf_token(client)
    return client.post("/login", data={"username": username, "password": "pass", "csrf_token": token}, follow_redirects=True)


def csrf_headers(client):
    return {"X-CSRF-Token": csrf_token(client, "/")}
