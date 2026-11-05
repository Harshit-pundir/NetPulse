"""FastAPI routes for the NetPulse dashboard and JSON API."""
import hmac
import ipaddress
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv
load_dotenv()

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from werkzeug.security import check_password_hash, generate_password_hash

from .database import supabase
from .schemas import DeviceInput, MonitoringInput, RegistrationInput
from .services.monitoring_service import monitor_all_devices, should_start_monitoring, start_scheduler, stop_scheduler
from .services.uptime_service import uptime_for

ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))
templates.env.globals["url_for"] = lambda endpoint, **kwargs: f"/static/{kwargs.get('filename', '')}"
DEVICE_TYPES = {"ROUTER", "SWITCH", "SERVER", "PC", "ACCESS_POINT", "OTHER"}


class Guest:
    is_authenticated = False
    username = ""
    role = "VIEWER"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A small read verifies the configured Supabase project without changing its schema.
    if not app.state.config.get("TESTING", False):
        _execute(supabase.table("devices").select("id").limit(1))
        if should_start_monitoring(app):
            start_scheduler(app)
    yield
    if not app.state.config.get("TESTING", False):
        stop_scheduler(app)


app = FastAPI(title="NetPulse API", description="Network health dashboard and device monitoring API.", version="1.0.0", lifespan=lifespan)
router = APIRouter()
app.state.config = {
    "START_MONITORING": os.getenv("START_MONITORING", "true").lower() not in {"0", "false", "no"},
    "MONITOR_INTERVAL": int(os.getenv("MONITOR_INTERVAL", "10")),
    "LATENCY_WARNING_MS": float(os.getenv("LATENCY_WARNING_MS", "100")),
    "LATENCY_CRITICAL_MS": float(os.getenv("LATENCY_CRITICAL_MS", "200")),
}
session_secret = os.getenv("SECRET_KEY")
if not session_secret or session_secret in {"change-me", "dev-change-this-secret"}:
    raise RuntimeError("Set a private SECRET_KEY in .env before starting NetPulse.")
app.add_middleware(SessionMiddleware, secret_key=session_secret, same_site="lax", https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


@app.middleware("http")
async def set_guest(request: Request, call_next):
    request.state.user = Guest()
    return await call_next(request)


def _execute(query):
    """Run one Supabase query and convert remote errors to a safe API error."""
    try:
        return query.execute()
    except Exception as error:
        # Do not return provider details because they can contain private connection data.
        raise HTTPException(503, "Supabase database request failed") from error


def _rows(query):
    return _execute(query).data or []


def _one(table: str, row_id: int):
    rows = _rows(supabase.table(table).select("*").eq("id", row_id).limit(1))
    return rows[0] if rows else None


def _device_names():
    rows = _rows(supabase.table("devices").select("id,name,ip_address"))
    return {item["id"]: item for item in rows}


def _activity(device_id, event_type, message):
    _execute(supabase.table("activity_logs").insert({
        "device_id": device_id, "event_type": event_type, "message": message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }))


def page(request: Request, name: str, **context):
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_urlsafe(32)
    user = _session_user(request)
    messages = request.session.pop("flash_messages", [])
    def get_flashed_messages(with_categories=False):
        return messages if with_categories else [message for _category, message in messages]
    values = {"request": request, "csrf_token": request.session["csrf_token"], "current_user": user,
              "get_flashed_messages": get_flashed_messages}
    values.update(context)
    return templates.TemplateResponse(request=request, name=name, context=values)


def _session_user(request: Request):
    if request.state.user.is_authenticated:
        return request.state.user
    user_id = request.session.get("user_id")
    if user_id:
        users = _rows(supabase.table("users").select("id,username,role").eq("id", user_id).limit(1))
        if users:
            request.state.user = SimpleNamespace(is_authenticated=True, username=users[0]["username"], role=users[0].get("role", "VIEWER"))
        else:
            request.session.clear()
    return request.state.user


def require_user(request: Request, api=False):
    _session_user(request)
    if not request.state.user.is_authenticated:
        if api:
            raise HTTPException(401, "Authentication required")
        return False
    return True


def require_admin(request: Request):
    require_user(request, api=True)
    if request.state.user.role != "ADMIN":
        raise HTTPException(403, "Administrator access required")


async def validate_csrf(request: Request):
    expected = request.session.get("csrf_token", "")
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied and request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        supplied = str((await request.form()).get("csrf_token", ""))
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(400, "The form expired or its security token was missing. Refresh and try again.")


def _check_csrf_header(request: Request):
    expected = request.session.get("csrf_token", "")
    supplied = request.headers.get("X-CSRF-Token", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(400, "The form expired or its security token was missing. Refresh and try again.")


def device_json(device):
    return {"id": device["id"], "name": device["name"], "ip_address": device["ip_address"],
            "hostname": device.get("hostname"), "device_type": device["device_type"],
            "location": device.get("location"), "description": device.get("description"),
            "monitoring_enabled": device.get("monitoring_enabled", True), "status": device.get("status", "UNKNOWN"),
            "current_latency": device.get("current_latency"), "last_checked_at": device.get("last_checked_at")}


def page_or_redirect(request, name, **context):
    if not require_user(request):
        return RedirectResponse("/login", status_code=303)
    return page(request, name, **context)


@router.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return page_or_redirect(request, "dashboard.html")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if require_user(request):
        return RedirectResponse("/", status_code=303)
    return page(request, "login.html")


@router.post("/login", tags=["Authentication"], description="Sign in with an existing users-table account.")
async def login(request: Request):
    await validate_csrf(request)
    form = await request.form()
    username = str(form.get("username", "")).strip()
    users = _rows(supabase.table("users").select("*").eq("username", username).limit(1))
    user = users[0] if users else None
    if user and check_password_hash(user["password_hash"], str(form.get("password", ""))):
        request.session["user_id"] = user["id"]
        return RedirectResponse("/", status_code=303)
    request.session["flash_messages"] = [("error", "Invalid username or password.")]
    return page(request, "login.html")


@router.post("/register", tags=["Authentication"], description="Create a viewer account in the existing users table.")
async def register(payload: RegistrationInput, request: Request):
    await validate_csrf(request)
    username = payload.username.strip()
    if not username:
        raise HTTPException(400, "Username is required")
    existing = _rows(supabase.table("users").select("id").eq("username", username).limit(1))
    if existing:
        raise HTTPException(409, "Username already exists")
    _execute(supabase.table("users").insert({
        "username": username, "password_hash": generate_password_hash(payload.password),
        "role": "VIEWER", "created_at": datetime.now(timezone.utc).isoformat(),
    }))
    return JSONResponse({"message": "Account created. Please sign in."}, status_code=201)


@router.post("/logout", tags=["Authentication"])
async def logout(request: Request):
    await validate_csrf(request)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/devices", response_class=HTMLResponse)
def devices_page(request: Request):
    return page_or_redirect(request, "devices.html", types=sorted(DEVICE_TYPES))


@router.get("/devices/{device_id}", response_class=HTMLResponse)
def device_page(device_id: int, request: Request):
    if not require_user(request):
        return RedirectResponse("/login", status_code=303)
    device = _one("devices", device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    return page(request, "device_details.html", device=device)


@router.get("/alerts", response_class=HTMLResponse)
def alerts_page(request: Request):
    if not require_user(request):
        return RedirectResponse("/login", status_code=303)
    devices = _rows(supabase.table("devices").select("*").order("name"))
    return page(request, "alerts.html", devices=devices)


@router.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request):
    if not require_user(request):
        return RedirectResponse("/login", status_code=303)
    devices = _rows(supabase.table("devices").select("*").order("name"))
    return page(request, "logs.html", devices=devices)


@router.get("/api/dashboard/summary", tags=["Dashboard"], description="Current device health totals and inventory.")
def summary(request: Request):
    require_user(request, True)
    devices = _rows(supabase.table("devices").select("*"))
    counts = {key: sum(item.get("status", "UNKNOWN") == key for item in devices) for key in ("ONLINE", "OFFLINE", "WARNING", "CRITICAL", "UNKNOWN")}
    latencies = [item["current_latency"] for item in devices if item.get("current_latency") is not None]
    active_count = _execute(supabase.table("alerts").select("id", count="exact").eq("acknowledged", False)).count
    return {"total": len(devices), "online": counts["ONLINE"], "offline": counts["OFFLINE"],
            "warning": counts["WARNING"], "critical": counts["CRITICAL"], "unknown": counts["UNKNOWN"],
            "active_alerts": active_count or 0, "average_latency": round(sum(latencies) / len(latencies), 1) if latencies else None,
            "devices": [device_json(item) for item in devices]}


@router.get("/api/dashboard/latency", tags=["Dashboard"])
def latency_api(request: Request):
    require_user(request, True)
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    rows = _rows(supabase.table("monitoring_results").select("*").gte("checked_at", since).order("checked_at", desc=True).limit(100))
    names = _device_names()
    points = [{"time": item["checked_at"], "latency": item["latency"], "device": names.get(item["device_id"], {}).get("name", "Unknown")} for item in reversed(rows) if item.get("latency") is not None]
    return {"points": points}


@router.get("/api/dashboard/alerts", tags=["Dashboard"])
def recent_alerts(request: Request):
    require_user(request, True)
    rows = _rows(supabase.table("alerts").select("*").order("created_at", desc=True).limit(8))
    names = _device_names()
    return {"alerts": [{"id": a["id"], "device": names.get(a["device_id"], {}).get("name", "Unknown"),
                         "severity": a["severity"], "message": a["message"], "acknowledged": a["acknowledged"],
                         "created_at": a["created_at"]} for a in rows]}


@router.get("/api/dashboard/activity", tags=["Dashboard"])
def dashboard_activity(request: Request):
    require_user(request, True)
    rows = _rows(supabase.table("activity_logs").select("*").order("created_at", desc=True).limit(8))
    names = _device_names()
    return {"activity": [{"device": names.get(item.get("device_id"), {}).get("name", "System"),
                           "event_type": item["event_type"], "message": item["message"], "created_at": item["created_at"]} for item in rows]}


@router.get("/api/devices", tags=["Devices"], description="List devices with search and status filters.")
def list_devices(request: Request, search: str = "", status: str | None = None, page: int = 1):
    require_user(request, True)
    size = 15
    query = supabase.table("devices").select("*", count="exact")
    if search.strip():
        safe_search = search.strip().replace(",", "").replace("(", "").replace(")", "")
        query = query.or_(f"name.ilike.%{safe_search}%,ip_address.ilike.%{safe_search}%")
    if status:
        query = query.eq("status", status)
    page = max(page, 1)
    result = _execute(query.order("name").range((page - 1) * size, page * size - 1))
    total = result.count if result.count is not None else len(result.data or [])
    return {"devices": [device_json(item) for item in (result.data or [])], "page": page,
            "pages": (total + size - 1) // size, "total": total}


def valid_target(value):
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return bool(value and len(value) <= 253 and all(
            len(label) <= 63 and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
            for label in value.rstrip(".").split(".")))


@router.post("/api/devices", status_code=201, tags=["Devices"], description="Add a device to the monitoring inventory.")
def create_device(payload: DeviceInput, request: Request):
    _check_csrf_header(request)
    require_admin(request)
    fields = payload.model_dump()
    fields["name"] = fields["name"].strip()
    fields["ip_address"] = fields["ip_address"].strip()
    if not valid_target(fields["ip_address"]):
        raise HTTPException(422, "A valid IP address or hostname is required")
    for field in ("hostname", "location", "description"):
        if fields.get(field) is not None:
            fields[field] = fields[field].strip() or None
    now = datetime.now(timezone.utc).isoformat()
    fields.update({"monitoring_enabled": True, "status": "UNKNOWN", "current_latency": None,
                   "last_checked_at": None, "created_at": now, "updated_at": now})
    duplicate_name = _rows(supabase.table("devices").select("id").eq("name", fields["name"]).limit(1))
    duplicate_ip = _rows(supabase.table("devices").select("id").eq("ip_address", fields["ip_address"]).limit(1))
    if duplicate_name or duplicate_ip:
        raise HTTPException(409, "A device with that name or address already exists.")
    created = _rows(supabase.table("devices").insert(fields))
    device = created[0]
    _activity(device["id"], "DEVICE_ADDED", f"{device['name']} added.")
    return device_json(device)


@router.get("/api/devices/{device_id}", tags=["Devices"])
def get_device(device_id: int, request: Request):
    require_user(request, True)
    device = _one("devices", device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    return device_json(device)


@router.put("/api/devices/{device_id}", tags=["Devices"], description="Update a device in the inventory.")
def update_device(device_id: int, payload: DeviceInput, request: Request):
    _check_csrf_header(request)
    require_admin(request)
    device = _one("devices", device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    fields = payload.model_dump()
    fields["name"] = fields["name"].strip()
    fields["ip_address"] = fields["ip_address"].strip()
    if not valid_target(fields["ip_address"]):
        raise HTTPException(422, "A valid IP address or hostname is required")
    duplicate_name = _rows(supabase.table("devices").select("id").neq("id", device_id).eq("name", fields["name"]).limit(1))
    duplicate_ip = _rows(supabase.table("devices").select("id").neq("id", device_id).eq("ip_address", fields["ip_address"]).limit(1))
    if duplicate_name or duplicate_ip:
        raise HTTPException(409, "A device with that name or address already exists.")
    for field in ("hostname", "location", "description"):
        if fields.get(field) is not None:
            fields[field] = fields[field].strip() or None
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = _rows(supabase.table("devices").update(fields).eq("id", device_id))
    return device_json(updated[0] if updated else {**device, **fields})


@router.delete("/api/devices/{device_id}", status_code=204, tags=["Devices"])
def delete_device(device_id: int, request: Request):
    _check_csrf_header(request)
    require_admin(request)
    if not _one("devices", device_id):
        raise HTTPException(404, "Device not found")
    # Delete dependent history first, matching the existing device-delete behavior.
    for table in ("monitoring_results", "alerts", "activity_logs"):
        _execute(supabase.table(table).delete().eq("device_id", device_id))
    _execute(supabase.table("devices").delete().eq("id", device_id))
    return Response(status_code=204)


@router.patch("/api/devices/{device_id}/monitoring", tags=["Devices"])
def toggle_monitoring(device_id: int, payload: MonitoringInput, request: Request):
    _check_csrf_header(request)
    require_admin(request)
    device = _one("devices", device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    updated = _rows(supabase.table("devices").update({"monitoring_enabled": payload.monitoring_enabled}).eq("id", device_id))
    state = "enabled" if payload.monitoring_enabled else "disabled"
    _activity(device_id, "MONITORING_TOGGLED", f"Monitoring {state}.")
    return device_json(updated[0] if updated else {**device, "monitoring_enabled": payload.monitoring_enabled})


@router.get("/api/devices/{device_id}/history", tags=["Devices"])
def history(device_id: int, request: Request, hours: int = 24):
    require_user(request, True)
    if not _one("devices", device_id):
        raise HTTPException(404, "Device not found")
    since = (datetime.now(timezone.utc) - timedelta(hours=max(1, min(hours, 168)))).isoformat()
    rows = _rows(supabase.table("monitoring_results").select("*").eq("device_id", device_id).gte("checked_at", since).order("checked_at").limit(500))
    return {"history": [{"status": row["status"], "latency": row.get("latency"), "checked_at": row["checked_at"]} for row in rows]}


@router.get("/api/devices/{device_id}/uptime", tags=["Devices"])
def device_uptime(device_id: int, request: Request):
    require_user(request, True)
    if not _one("devices", device_id):
        raise HTTPException(404, "Device not found")
    return {str(hours): uptime_for(device_id, hours) for hours in (1, 24, 168)}


@router.get("/api/alerts", tags=["Alerts"], description="Filter and page through device alerts.")
def list_alerts(request: Request, severity: str | None = None, device_id: int | None = None, acknowledged: bool | None = None, page: int = 1):
    require_user(request, True)
    size = 20
    query = supabase.table("alerts").select("*", count="exact")
    if severity:
        query = query.eq("severity", severity)
    if device_id:
        query = query.eq("device_id", device_id)
    if acknowledged is not None:
        query = query.eq("acknowledged", acknowledged)
    page = max(page, 1)
    result = _execute(query.order("created_at", desc=True).range((page - 1) * size, page * size - 1))
    names = _device_names()
    rows = [{"id": alert["id"], "device": names.get(alert["device_id"], {}).get("name", "Unknown"),
             "alert_type": alert["alert_type"], "severity": alert["severity"], "message": alert["message"],
             "acknowledged": alert["acknowledged"], "created_at": alert["created_at"]} for alert in (result.data or [])]
    total = result.count if result.count is not None else len(rows)
    return {"alerts": rows, "total": total, "pages": (total + size - 1) // size}


@router.patch("/api/alerts/{alert_id}/acknowledge", tags=["Alerts"])
def acknowledge_alert(alert_id: int, request: Request):
    _check_csrf_header(request)
    require_admin(request)
    alert = _one("alerts", alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    if not alert.get("acknowledged"):
        now = datetime.now(timezone.utc).isoformat()
        _execute(supabase.table("alerts").update({"acknowledged": True, "acknowledged_at": now}).eq("id", alert_id))
        _activity(alert["device_id"], "ALERT_ACKNOWLEDGED", f"Alert acknowledged: {alert['message']}")
    return {"id": alert_id, "acknowledged": True}


@router.get("/api/logs", tags=["Activity logs"])
def list_logs(request: Request, device_id: int | None = None, search: str = "", page: int = 1):
    require_user(request, True)
    size = 25
    query = supabase.table("activity_logs").select("*", count="exact")
    if device_id:
        query = query.eq("device_id", device_id)
    if search.strip():
        query = query.ilike("message", f"%{search.strip()}%")
    page = max(page, 1)
    result = _execute(query.order("created_at", desc=True).range((page - 1) * size, page * size - 1))
    names = _device_names()
    rows = [{"id": item["id"], "device": names.get(item.get("device_id"), {}).get("name", "System"),
             "ip": names.get(item.get("device_id"), {}).get("ip_address", "-"), "event_type": item["event_type"],
             "message": item["message"], "created_at": item["created_at"]} for item in (result.data or [])]
    total = result.count if result.count is not None else len(rows)
    return {"logs": rows, "total": total, "pages": (total + size - 1) // size}


@router.get("/health", tags=["System"], include_in_schema=False)
def health():
    return {"status": "ok"}


app.include_router(router)


@app.exception_handler(HTTPException)
async def http_error(_request, error):
    return JSONResponse({"error": error.detail}, status_code=error.status_code, headers=error.headers)


@app.exception_handler(RequestValidationError)
async def invalid_request(_request, _error):
    return JSONResponse({"error": "Invalid request data."}, status_code=422)
