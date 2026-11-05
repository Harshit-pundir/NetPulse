import hmac
import os
import secrets
import ipaddress
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv
load_dotenv()

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select, func, text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from werkzeug.security import check_password_hash, generate_password_hash

from .database import engine, get_db
from .models import ActivityLog, Alert, Device, MonitoringResult, User
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
    testing = bool(app.dependency_overrides)
    if not testing:
        # Verify PostgreSQL is reachable without changing the existing schema.
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    if not testing and should_start_monitoring(app, False):
        start_scheduler(app)
    yield
    if not testing:
        stop_scheduler(app)


app = FastAPI(title="NetPulse API", description="Network health dashboard and device monitoring API.", version="1.0.0", lifespan=lifespan)
router = APIRouter()
app.state.config = {"START_MONITORING": os.getenv("START_MONITORING", "true").lower() not in {"0", "false", "no"}, "MONITOR_INTERVAL": int(os.getenv("MONITOR_INTERVAL", "10")), "LATENCY_WARNING_MS": float(os.getenv("LATENCY_WARNING_MS", "100")), "LATENCY_CRITICAL_MS": float(os.getenv("LATENCY_CRITICAL_MS", "200"))}
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-change-this-secret"), same_site="lax", https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


@app.middleware("http")
async def session_and_csrf(request: Request, call_next):
    request.state.user = Guest()
    return await call_next(request)


def page(request: Request, name: str, **context):
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_urlsafe(32)
    user = request.state.user
    if not user.is_authenticated and request.session.get("user_id"):
        user = SimpleNamespace(is_authenticated=True, username=request.session.get("username", ""), role=request.session.get("role", "VIEWER"))
        request.state.user = user
    values = {"request": request, "csrf_token": request.session["csrf_token"], "current_user": user, "get_flashed_messages": lambda **kwargs: []}
    values.update(context)
    return templates.TemplateResponse(request=request, name=name, context=values)


def require_user(request: Request, api=False):
    if not request.state.user.is_authenticated and request.session.get("user_id"):
        request.state.user = SimpleNamespace(is_authenticated=True, username=request.session.get("username", ""), role=request.session.get("role", "VIEWER"))
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
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_urlsafe(32)
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied and request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        form = await request.form()
        supplied = str(form.get("csrf_token", ""))
    if not supplied or not hmac.compare_digest(request.session["csrf_token"], supplied):
        raise HTTPException(400, "The form expired or its security token was missing. Refresh and try again.")


def device_json(device):
    return {"id": device.id, "name": device.name, "ip_address": device.ip_address, "hostname": device.hostname,
            "device_type": device.device_type, "location": device.location, "description": device.description,
            "monitoring_enabled": device.monitoring_enabled, "status": device.status,
            "current_latency": device.current_latency, "last_checked_at": device.last_checked_at.isoformat() if device.last_checked_at else None}


def page_or_redirect(request, name, **context):
    if not require_user(request):
        return RedirectResponse("/login", status_code=303)
    return page(request, name, **context)


@router.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return page_or_redirect(request, "dashboard.html")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.state.user.is_authenticated:
        return RedirectResponse("/", status_code=303)
    return page(request, "login.html")


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    await validate_csrf(request)
    form = await request.form()
    user = db.scalar(select(User).where(User.username == str(form.get("username", "")).strip()))
    if user and check_password_hash(user.password_hash, str(form.get("password", ""))):
        request.session["user_id"] = user.id
        request.session["username"] = user.username
        request.session["role"] = user.role
        return RedirectResponse("/", status_code=303)
    return page(request, "login.html")


@router.post("/register", tags=["Authentication"], description="Create a viewer account.")
async def register(payload: RegistrationInput, request: Request, db: Session = Depends(get_db)):
    await validate_csrf(request)
    username, password = payload.username.strip(), payload.password
    if not username:
        raise HTTPException(400, "Username is required")
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, "Username already exists")
    user = User(username=username, password_hash=generate_password_hash(password), role="VIEWER")
    db.add(user); db.commit()
    return JSONResponse({"message": "Account created. Please sign in."}, status_code=201)


@router.post("/logout")
async def logout(request: Request):
    await validate_csrf(request)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/devices", response_class=HTMLResponse)
def devices_page(request: Request):
    return page_or_redirect(request, "devices.html", types=sorted(DEVICE_TYPES))


@router.get("/devices/{device_id}", response_class=HTMLResponse)
def device_page(device_id: int, request: Request, db: Session = Depends(get_db)):
    if not require_user(request): return RedirectResponse("/login", status_code=303)
    device = db.get(Device, device_id)
    if not device: raise HTTPException(404, "Device not found")
    return page(request, "device_details.html", device=device)


@router.get("/alerts", response_class=HTMLResponse)
def alerts_page(request: Request, db: Session = Depends(get_db)):
    return page_or_redirect(request, "alerts.html", devices=db.scalars(select(Device).order_by(Device.name)).all())


@router.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request, db: Session = Depends(get_db)):
    return page_or_redirect(request, "logs.html", devices=db.scalars(select(Device).order_by(Device.name)).all())


@router.get("/api/dashboard/summary", tags=["Dashboard"], description="Current device health totals and inventory.")
def summary(request: Request, db: Session = Depends(get_db)):
    require_user(request, True); devices = db.scalars(select(Device)).all()
    counts = {key: sum(item.status == key for item in devices) for key in ("ONLINE", "OFFLINE", "WARNING", "CRITICAL", "UNKNOWN")}
    latency = [item.current_latency for item in devices if item.current_latency is not None]
    return {"total": len(devices), "online": counts["ONLINE"], "offline": counts["OFFLINE"], "warning": counts["WARNING"], "critical": counts["CRITICAL"], "unknown": counts["UNKNOWN"], "active_alerts": db.scalar(select(func.count()).select_from(Alert).where(Alert.acknowledged.is_(False))), "average_latency": round(sum(latency) / len(latency), 1) if latency else None, "devices": [device_json(item) for item in devices]}


@router.get("/api/dashboard/latency", tags=["Dashboard"])
def latency_api(request: Request, db: Session = Depends(get_db)):
    require_user(request, True); since = datetime.utcnow() - timedelta(hours=24)
    results = db.scalars(select(MonitoringResult).where(MonitoringResult.checked_at >= since, MonitoringResult.latency.is_not(None)).order_by(MonitoringResult.checked_at.desc()).limit(100)).all()
    return {"points": [{"time": item.checked_at.isoformat(), "latency": item.latency, "device": item.device.name} for item in reversed(results)]}


@router.get("/api/dashboard/alerts", tags=["Dashboard"])
def recent_alerts(request: Request, db: Session = Depends(get_db)):
    require_user(request, True); rows = db.scalars(select(Alert).order_by(Alert.created_at.desc()).limit(8)).all()
    return {"alerts": [{"id": a.id, "device": a.device.name, "severity": a.severity, "message": a.message, "acknowledged": a.acknowledged, "created_at": a.created_at.isoformat()} for a in rows]}


@router.get("/api/dashboard/activity", tags=["Dashboard"])
def dashboard_activity(request: Request, db: Session = Depends(get_db)):
    require_user(request, True); rows = db.scalars(select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(8)).all()
    return {"activity": [{"device": item.device.name if item.device else "System", "event_type": item.event_type, "message": item.message, "created_at": item.created_at.isoformat()} for item in rows]}


@router.get("/api/devices", tags=["Devices"], description="List devices with optional search and status filters.")
def list_devices(request: Request, search: str = "", status: str | None = None, page: int = 1, db: Session = Depends(get_db)):
    require_user(request, True); query = select(Device)
    if search.strip(): query = query.where(or_(Device.name.ilike(f"%{search.strip()}%"), Device.ip_address.ilike(f"%{search.strip()}%")))
    if status: query = query.where(Device.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(Device.name).offset((max(1,page)-1)*15).limit(15)).all()
    return {"devices": [device_json(item) for item in rows], "page": max(1,page), "pages": (total+14)//15, "total": total}


def valid_target(value):
    try: ipaddress.ip_address(value); return True
    except ValueError:
        return bool(value and len(value) <= 253 and all(len(label) <= 63 and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label) for label in value.rstrip(".").split(".")))


@router.post("/api/devices", status_code=201, tags=["Devices"], description="Add a device to the monitoring inventory.")
def create_device(payload: DeviceInput, request: Request, db: Session = Depends(get_db)):
    csrf, expected = request.headers.get("X-CSRF-Token", ""), request.session.get("csrf_token", "")
    if not expected or not csrf or not hmac.compare_digest(expected, csrf): raise HTTPException(400, "The form expired or its security token was missing. Refresh and try again.")
    require_admin(request); fields = payload.model_dump()
    if not valid_target(fields["ip_address"]): raise HTTPException(422, "A valid IP address or hostname is required")
    for key in ("name", "ip_address"): fields[key] = fields[key].strip()
    if db.scalar(select(Device).where(or_(Device.name == fields["name"], Device.ip_address == fields["ip_address"]))): raise HTTPException(409, "A device with that name or address already exists.")
    device = Device(**fields); db.add(device); db.flush(); db.add(ActivityLog(device_id=device.id, event_type="DEVICE_ADDED", message=f"{device.name} added.")); db.commit(); db.refresh(device)
    return device_json(device)


@router.get("/api/devices/{device_id}", tags=["Devices"])
def get_device(device_id: int, request: Request, db: Session = Depends(get_db)):
    require_user(request, True); device = db.get(Device, device_id)
    if not device: raise HTTPException(404, "Device not found")
    return device_json(device)


@router.put("/api/devices/{device_id}", tags=["Devices"], description="Update a device in the inventory.")
def update_device(device_id: int, payload: DeviceInput, request: Request, db: Session = Depends(get_db)):
    csrf, expected = request.headers.get("X-CSRF-Token", ""), request.session.get("csrf_token", "")
    if not expected or not csrf or not hmac.compare_digest(expected, csrf): raise HTTPException(400, "The form expired or its security token was missing. Refresh and try again.")
    require_admin(request); device = db.get(Device, device_id)
    if not device: raise HTTPException(404, "Device not found")
    fields = payload.model_dump()
    if not valid_target(fields["ip_address"]): raise HTTPException(422, "A valid IP address or hostname is required")
    duplicate = db.scalar(select(Device).where(Device.id != device_id, or_(Device.name == fields["name"], Device.ip_address == fields["ip_address"])))
    if duplicate: raise HTTPException(409, "A device with that name or address already exists.")
    for key, value in fields.items(): setattr(device, key, value.strip() if isinstance(value, str) else value)
    db.commit(); db.refresh(device); return device_json(device)


@router.delete("/api/devices/{device_id}", status_code=204, tags=["Devices"])
def delete_device(device_id: int, request: Request, db: Session = Depends(get_db)):
    csrf, expected = request.headers.get("X-CSRF-Token", ""), request.session.get("csrf_token", "")
    if not expected or not csrf or not hmac.compare_digest(expected, csrf): raise HTTPException(400, "The form expired or its security token was missing. Refresh and try again.")
    require_admin(request); device = db.get(Device, device_id)
    if not device: raise HTTPException(404, "Device not found")
    db.delete(device); db.commit(); return Response(status_code=204)


@router.patch("/api/devices/{device_id}/monitoring", tags=["Devices"])
def toggle_monitoring(device_id: int, payload: MonitoringInput, request: Request, db: Session = Depends(get_db)):
    csrf, expected = request.headers.get("X-CSRF-Token", ""), request.session.get("csrf_token", "")
    if not expected or not csrf or not hmac.compare_digest(expected, csrf): raise HTTPException(400, "The form expired or its security token was missing. Refresh and try again.")
    require_admin(request); device = db.get(Device, device_id)
    if not device: raise HTTPException(404, "Device not found")
    device.monitoring_enabled = payload.monitoring_enabled; state = "enabled" if device.monitoring_enabled else "disabled"
    db.add(ActivityLog(device_id=device.id, event_type="MONITORING_TOGGLED", message=f"Monitoring {state}.")); db.commit(); db.refresh(device); return device_json(device)


@router.get("/api/devices/{device_id}/history", tags=["Devices"])
def history(device_id: int, request: Request, hours: int = 24, db: Session = Depends(get_db)):
    require_user(request, True)
    if not db.get(Device, device_id): raise HTTPException(404, "Device not found")
    since = datetime.utcnow() - timedelta(hours=max(1,min(hours,168)))
    rows = db.scalars(select(MonitoringResult).where(MonitoringResult.device_id == device_id, MonitoringResult.checked_at >= since).order_by(MonitoringResult.checked_at).limit(500)).all()
    return {"history": [{"status": x.status, "latency": x.latency, "checked_at": x.checked_at.isoformat()} for x in rows]}


@router.get("/api/devices/{device_id}/uptime", tags=["Devices"])
def device_uptime(device_id: int, request: Request, db: Session = Depends(get_db)):
    require_user(request, True)
    if not db.get(Device, device_id): raise HTTPException(404, "Device not found")
    return {str(hours): uptime_for(db, device_id, hours) for hours in (1, 24, 168)}


@router.get("/api/alerts", tags=["Alerts"], description="Filter and page through device alerts.")
def list_alerts(request: Request, severity: str | None = None, device_id: int | None = None, acknowledged: bool | None = None, page: int = 1, db: Session = Depends(get_db)):
    require_user(request, True); query = select(Alert)
    if severity: query = query.where(Alert.severity == severity)
    if device_id: query = query.where(Alert.device_id == device_id)
    if acknowledged is not None: query = query.where(Alert.acknowledged == acknowledged)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(Alert.created_at.desc()).offset((max(1,page)-1)*20).limit(20)).all()
    return {"alerts": [{"id": a.id, "device": a.device.name, "alert_type": a.alert_type, "severity": a.severity, "message": a.message, "acknowledged": a.acknowledged, "created_at": a.created_at.isoformat()} for a in rows], "total": total, "pages": (total+19)//20}


@router.patch("/api/alerts/{alert_id}/acknowledge", tags=["Alerts"])
def acknowledge_alert(alert_id: int, request: Request, db: Session = Depends(get_db)):
    csrf, expected = request.headers.get("X-CSRF-Token", ""), request.session.get("csrf_token", "")
    if not expected or not csrf or not hmac.compare_digest(expected, csrf): raise HTTPException(400, "The form expired or its security token was missing. Refresh and try again.")
    require_admin(request); alert = db.get(Alert, alert_id)
    if not alert: raise HTTPException(404, "Alert not found")
    if not alert.acknowledged:
        alert.acknowledged = True; alert.acknowledged_at = datetime.utcnow(); db.add(ActivityLog(device_id=alert.device_id, event_type="ALERT_ACKNOWLEDGED", message=f"Alert acknowledged: {alert.message}")); db.commit()
    return {"id": alert.id, "acknowledged": True}


@router.get("/api/logs", tags=["Activity logs"])
def list_logs(request: Request, device_id: int | None = None, search: str = "", page: int = 1, db: Session = Depends(get_db)):
    require_user(request, True); query = select(ActivityLog)
    if device_id: query = query.where(ActivityLog.device_id == device_id)
    if search.strip(): query = query.where(ActivityLog.message.ilike(f"%{search.strip()}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(ActivityLog.created_at.desc()).offset((max(1,page)-1)*25).limit(25)).all()
    return {"logs": [{"id": x.id, "device": x.device.name if x.device else "System", "ip": x.device.ip_address if x.device else "-", "event_type": x.event_type, "message": x.message, "created_at": x.created_at.isoformat()} for x in rows], "total": total, "pages": (total+24)//25}


@router.get("/health", tags=["System"], include_in_schema=False)
def health(): return {"status": "ok"}


app.include_router(router)


@app.exception_handler(HTTPException)
async def http_error(_request, error):
    return JSONResponse({"error": error.detail}, status_code=error.status_code, headers=error.headers)
