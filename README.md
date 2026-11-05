# NetPulse

NetPulse checks network devices, records latency and availability in Supabase PostgreSQL, and displays results in the existing HTML dashboard.

## Stack and structure

- FastAPI serves the pages and JSON APIs; `/docs` and `/redoc` show interactive API documentation.
- SQLAlchemy maps the existing `users`, `devices`, `monitoring_results`, `alerts`, and `activity_logs` tables.
- Jinja2 renders the original pages. Existing CSS and vanilla JavaScript remain in `app/static`.
- `app/main.py` contains the routes and application setup; `app/database.py` creates database sessions; `app/models.py` describes database rows; `app/schemas.py` validates device input; `app/services` contains monitoring and alert rules.

## Setup

Use Python 3.11 or newer. Create `.env` from `.env.example` and enter the existing Supabase PostgreSQL URL and a long random secret. Keep `.env` private.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and set DATABASE_URL, SECRET_KEY, and INITIAL_ADMIN_PASSWORD.
python init_db.py
python run.py
```

Open http://127.0.0.1:8000. The app checks database connectivity at startup and does not create, drop, or rebuild tables. Keep the existing Supabase schema and connection string in `.env`.

`.env` settings: `DATABASE_URL`, `SECRET_KEY`, `INITIAL_ADMIN_PASSWORD`, `MONITOR_INTERVAL` (seconds), `LATENCY_WARNING_MS`, `LATENCY_CRITICAL_MS`, `START_MONITORING`, and optionally `COOKIE_SECURE=true` behind HTTPS.

## API and workflow

The browser sends same-origin fetch requests to the FastAPI JSON routes. FastAPI checks the signed session cookie, validates input with Pydantic, and uses a short-lived SQLAlchemy session to read or write PostgreSQL. Server-rendered pages use the same Jinja templates as before.

Important APIs include `/api/dashboard/summary`, `/api/dashboard/activity`, `/api/devices`, `/api/alerts`, and `/api/logs`. Device create, update, delete, acknowledgement, and monitoring controls require an administrator. All state-changing browser requests include the CSRF token rendered into the page.

FastAPI documentation: http://127.0.0.1:8000/docs and http://127.0.0.1:8000/redoc.

## Monitoring

At startup, one background thread periodically reads enabled device IDs, pings each device, and saves a result using a separate SQLAlchemy session per check. A failure for one device is logged and does not prevent other checks. Alert rules run on status transitions, so repeated failures do not create repeated active alerts. On shutdown the app signals the thread and waits up to five seconds.

Ping may be blocked by a firewall or network policy. Latency is measured from the computer running NetPulse.

## Tests

```powershell
pytest
```
