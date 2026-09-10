# NetPulse

NetPulse is a lightweight Flask dashboard for monitoring network devices. It checks whether devices respond to `ping`, stores latency and status history, and shows alerts when a device goes down, recovers, or becomes slow.

## Run the project

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python init_db.py
python run.py
```

Open `http://127.0.0.1:5000`.

Development accounts:

- Admin: `admin` / `admin123`
- Viewer: `viewer` / `viewer123`

Replace the seeded private-address devices with addresses reachable from the computer running NetPulse.

## Features

- Login and logout with hashed passwords
- Admin and viewer roles
- Add, edit, delete, search, and paginate devices
- Real ICMP reachability checks and latency measurement
- Status history, uptime calculation, device details, logs, and charts
- Device-down, recovery, and high-latency alerts
- Duplicate alert prevention and alert acknowledgement
- Dashboard auto-refresh with vanilla JavaScript

## Simple architecture

```text
Browser
   ↓
Flask Routes
   ↓
Services
   ↓
SQLAlchemy Models
   ↓
SQLite / MySQL
```

Monitoring flow:

```text
Scheduler
   ↓
Check Device
   ↓
Measure Latency
   ↓
Update Status
   ↓
Save Result
   ↓
Create Alert if Needed
```

## How the monitoring works

`run.py` starts one small background thread. Every `MONITOR_INTERVAL` seconds (10 by default), it finds enabled devices and calls `ping_host()` for each one. The service saves a `MonitoringResult`, updates the device's current status, and checks whether an alert is needed.

- No ping response means `OFFLINE`.
- A response over `LATENCY_WARNING_MS` (100 ms by default) means `WARNING`.
- Any other successful response means `ONLINE`.
- A down alert is created only when a reachable device changes to offline, so repeating failed checks do not create duplicates.
- When an offline device responds again, NetPulse creates a recovery alert and closes the active down alert.

Uptime is easy to calculate: successful (`ONLINE` or `WARNING`) checks divided by all checks in the selected period, multiplied by 100.

## How to understand the code

- `app/__init__.py` creates Flask and registers the routes.
- `app/models.py` defines the database tables: users, devices, results, alerts, and logs.
- `app/routes/` contains the web pages and JSON APIs. Routes validate input and return responses.
- `app/services/monitoring_service.py` contains the step-by-step ping and scheduler logic.
- `app/services/alert_service.py` contains the simple transition-based alert rules.
- `app/services/uptime_service.py` contains the uptime formula.
- `app/templates/` contains readable Jinja HTML pages.
- `app/static/js/` fetches JSON APIs and updates the page. No frontend framework is used.
- `app/static/css/style.css` contains the page styling grouped by section.
- `tests/` contains readable arrange-act-assert tests. Network calls are mocked, so tests do not need Internet access.

## APIs

- Dashboard: `GET /api/dashboard/summary`, `/latency`, `/alerts`, `/activity`
- Devices: `GET|POST /api/devices`, `GET|PUT|DELETE /api/devices/<id>`
- Monitoring: `PATCH /api/devices/<id>/monitoring`
- Device history: `GET /api/devices/<id>/history`, `/uptime`
- Alerts: `GET /api/alerts`, `PATCH /api/alerts/<id>/acknowledge`
- Logs: `GET /api/logs`

## Tests

Run:

```powershell
pytest
```

## Important limitation

Ping can be blocked by a firewall, operating system configuration, or network policy. Latency is measured from the computer running NetPulse, not from an external monitoring server.
