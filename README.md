# NetPulse

NetPulse is a Flask network-operations dashboard for managing devices, performing real ICMP reachability checks, retaining history, calculating uptime, and raising actionable alerts.

## Run it

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python init_db.py
python run.py
```

Open `http://127.0.0.1:5000`. Development accounts: `admin` / `admin123` and `viewer` / `viewer123`. Replace seeded private-address demo devices with devices reachable from the machine running NetPulse.

## Features and architecture

Flask + SQLAlchemy + Flask-Login provide the application layer; SQLite is the default database, while `DATABASE_URL` supports MySQL-compatible SQLAlchemy URLs. Models: User, Device, MonitoringResult, Alert, and ActivityLog. The dashboard uses Jinja templates, custom CSS, vanilla JavaScript, and Chart.js.

An application background thread runs at `MONITOR_INTERVAL` (default 10 seconds). It invokes the operating system's `ping` command with Windows/Linux-aware arguments, a strict timeout, and parses response time. Results are stored for every enabled device. Unreachable devices are OFFLINE; latency over `LATENCY_WARNING_MS` (100 ms) is WARNING. Transition-based alerts prevent repeated down/high-latency spam and create a recovery alert once a device returns. Uptime is online-or-warning checks divided by all checks in a selected window.

## APIs

`GET /api/dashboard/summary`, `/latency`, `/alerts`, `/activity`; `GET|POST /api/devices`; `GET|PUT|DELETE /api/devices/<id>`; `PATCH /api/devices/<id>/monitoring`; `GET /api/devices/<id>/history`, `/uptime`; `GET /api/alerts`; `PATCH /api/alerts/<id>/acknowledge`; and `GET /api/logs`.

## Tests

Run `pytest`. Network operations are mocked; tests do not need Internet access.

## Limitations

ICMP can be blocked by firewall, OS settings, network configuration, or security policy. Latency is measured from the NetPulse host—not a central external probe. Possible next steps include SNMP, port checks, notifications, topology, and host CPU/RAM collection.
