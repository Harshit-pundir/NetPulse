# NetPulse

NetPulse is a lightweight network monitoring dashboard built with Python, Flask, SQLAlchemy, Supabase PostgreSQL, HTML, CSS, vanilla JavaScript, and Chart.js. It checks devices with `ping`, records latency and status history, and creates useful alerts.

## Architecture

```text
Browser
   ↓
HTML + CSS + Vanilla JavaScript
   ↓
Flask
   ↓
SQLAlchemy
   ↓
Supabase PostgreSQL
```

The browser communicates only with Flask. Supabase is the hosted PostgreSQL database; no database credentials or Supabase service keys are sent to the browser.

Monitoring flow:

```text
Background Monitoring Worker
   ↓
Network Reachability Check
   ↓
Latency Measurement
   ↓
Device Status
   ↓
SQLAlchemy
   ↓
Supabase PostgreSQL
   ↓
Flask API
   ↓
Dashboard
```

## Supabase setup

1. Create a project at [Supabase](https://supabase.com/).
2. Open its database connection settings.
3. Copy the PostgreSQL connection string in `psycopg` SQLAlchemy format.
4. Copy `.env.example` to `.env`.
5. Put the connection string in `DATABASE_URL`. Never commit `.env`.
6. Run `python init_db.py`.
7. Start Flask with `python run.py`.

Example `.env` (placeholders only):

```env
SECRET_KEY=replace-with-a-long-random-value
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE
MONITOR_INTERVAL=10
LATENCY_WARNING_MS=100
LATENCY_CRITICAL_MS=200
```

Do not put Supabase API keys, service-role keys, passwords, or connection strings in source code, templates, JavaScript, or Git.

## Run locally

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and add the Supabase PostgreSQL DATABASE_URL.
python init_db.py
python run.py
```

Open `http://127.0.0.1:5000`.

`init_db.py` can be run repeatedly. It creates missing tables and only adds missing starter users and demo devices.

Development accounts:

- Admin: `admin` / `admin123`
- Viewer: `viewer` / `viewer123`

## Import old SQLite data

The old local database is not deleted. If you want to keep its data, configure `.env` first, then run:

```powershell
python import_sqlite.py instance/network_monitor.db
```

The importer copies users, devices, monitoring results, alerts, and activity logs in foreign-key order. It skips primary keys already present in PostgreSQL, so rerunning it does not duplicate imported rows.

## Database schema

| Table | Purpose |
| --- | --- |
| `users` | Login username, password hash, role, and creation time. |
| `devices` | Monitored devices and their current health. |
| `monitoring_results` | One saved reachability and latency check. |
| `alerts` | Device-down, recovery, and high-latency conditions. |
| `activity_logs` | A simple audit trail of device and alert events. |

```text
Device → MonitoringResult
Device → Alert
Device → ActivityLog
```

All application timestamps are stored as UTC values. The dashboard converts them to the browser's local time for display.

## How monitoring works

`run.py` starts one background thread. Every `MONITOR_INTERVAL` seconds it reads enabled devices from PostgreSQL, pings each device, saves a monitoring result, updates the latest device status, and applies alert rules.

- No ping response: `OFFLINE`
- Response over `LATENCY_WARNING_MS`: `WARNING`
- Other response: `ONLINE`
- Repeated failures do not duplicate a down alert.
- An offline device that responds again receives a recovery alert.

Uptime is successful (`ONLINE` or `WARNING`) checks divided by all checks in the requested period, multiplied by 100.

## Project guide

- `config.py` reads safe configuration from environment variables.
- `app/models.py` defines the PostgreSQL tables, indexes, and relationships.
- `app/routes/` contains Flask pages and JSON APIs.
- `app/services/monitoring_service.py` contains the ping worker.
- `app/services/alert_service.py` contains transition-based alert rules.
- `init_db.py` creates tables and starter data.
- `import_sqlite.py` is the optional one-time legacy data importer.
- `tests/` uses an isolated in-memory SQLite database and mocked network checks; production runtime uses Supabase PostgreSQL.

## APIs

- Dashboard: `GET /api/dashboard/summary`, `/latency`, `/alerts`, `/activity`
- Devices: `GET|POST /api/devices`, `GET|PUT|DELETE /api/devices/<id>`
- Monitoring: `PATCH /api/devices/<id>/monitoring`
- Device history: `GET /api/devices/<id>/history`, `/uptime`
- Alerts: `GET /api/alerts`, `PATCH /api/alerts/<id>/acknowledge`
- Logs: `GET /api/logs`

## Tests

```powershell
pytest
```

## Important limitation

Ping can be blocked by a firewall, operating system configuration, or network policy. Latency is measured from the computer running NetPulse, not from an external monitoring server.
