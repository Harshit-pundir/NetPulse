# NetPulse

NetPulse checks configured network devices and shows their current status, check history, alerts, and activity in a server-rendered dashboard.

## Technology

- FastAPI handles pages and JSON APIs.
- The official `supabase` Python package provides one shared client for the existing Supabase PostgreSQL project.
- Pydantic validates API input. Jinja2, HTML, CSS, and vanilla JavaScript provide the existing browser interface.
- A small Python background thread checks devices with the operating system's `ping` command.

The application keeps using the existing `users`, `devices`, `monitoring_results`, `alerts`, and `activity_logs` tables. Startup reads from the API to check connectivity; it does not create or reset tables.

## Project guide

- `app/main.py` contains FastAPI setup, browser pages, and API routes.
- `app/database.py` reads `SUPABASE_URL` and `SUPABASE_KEY` and creates the one shared `supabase` client.
- `app/schemas.py` checks incoming device and registration fields.
- `app/services/monitoring_service.py` runs the background device checks.
- `app/services/alert_service.py` applies status-change alert rules.
- `app/services/uptime_service.py` calculates uptime from saved check results.
- `init_db.py` can add the initial administrator row to the existing `users` table; it does not create tables.
- `app/templates/` contains Jinja2 pages. `app/static/` contains the existing CSS and JavaScript.

## Configure Supabase

For a fresh checkout only, copy `.env.example` to `.env`. In an existing checkout, keep the current `.env` and add `SUPABASE_URL` and `SUPABASE_KEY` from the existing Supabase project; also keep a long random `SECRET_KEY`. Never put the Supabase key in JavaScript, templates, logs, or Git. Keep `.env` private.

The key must have Data API access to the existing tables. If Row Level Security is enabled, configure policies for the chosen key. The app does not use Supabase Auth; it checks the existing `users.password_hash` values and keeps a signed browser session.

Settings include `MONITOR_INTERVAL` (seconds), `LATENCY_WARNING_MS`, `LATENCY_CRITICAL_MS`, `START_MONITORING`, and `COOKIE_SECURE` (set true behind HTTPS).

## Install and run

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# For a fresh checkout only: Copy-Item .env.example .env
# In an existing checkout, add required values to .env without replacing it.
python init_db.py
python run.py
```

Open http://127.0.0.1:8000. FastAPI docs are at http://127.0.0.1:8000/docs and http://127.0.0.1:8000/redoc.

## Request and monitoring flow

The browser sends requests to FastAPI. Routes check the cookie session and CSRF token, validate input with Pydantic, then use the shared `supabase` client for table reads or writes. FastAPI returns rendered HTML or JSON for the existing JavaScript.

At startup the app checks that the `devices` table can be read. One background thread then loads enabled devices, pings them, and writes each check through the same Supabase client. Status transitions create down, recovery, or high-latency alerts. A failed device check does not stop checks for other devices. Shutdown signals the thread and waits up to five seconds.

## Tests

```powershell
pytest
```

Tests use a fake in-memory Supabase client, so they do not need production credentials and never write to your project. A live connection check requires valid `SUPABASE_URL` and `SUPABASE_KEY` values in `.env`.
