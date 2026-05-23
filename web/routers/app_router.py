import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from web.auth import get_current_user
from web.templates_env import templates
from web import db
from modules.tracker.database import ApplicationTracker

router = APIRouter(prefix="/app")
tracker = ApplicationTracker()

FREE_RUNS_LIMIT = int(os.environ.get("FREE_RUNS_LIMIT", "3"))


def _auth(request: Request):
    user_token = get_current_user(request)
    if not user_token:
        raise Exception("unauth")
    user = db.get_user_by_id(user_token["sub"])
    if not user:
        raise Exception("user_not_found")
    return user_token, user


def _login_redirect():
    r = RedirectResponse("/login", status_code=302)
    r.delete_cookie("session")
    return r


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    try:
        user_token, user = _auth(request)
    except Exception:
        return _login_redirect()

    uid = user_token["sub"]
    stats = tracker.get_stats(user_id=uid)
    recent = tracker.get_applications(user_id=uid)[:10]
    profile = db.get_profile(uid)
    settings = db.get_settings(uid)

    runs_used = user.get("runs_used") or 0
    has_credentials = bool(
        settings.get("computrabajo_email") or
        settings.get("bumeran_email") or
        settings.get("zonajobs_email")
    )

    return templates.TemplateResponse(request, "app/dashboard.html", {
        "user": user,
        "stats": stats,
        "recent_apps": recent,
        "has_profile": profile is not None,
        "has_credentials": has_credentials,
        "runs_used": runs_used,
        "free_runs_limit": FREE_RUNS_LIMIT,
        "active": "dashboard",
    })


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding(request: Request):
    try:
        user_token, user = _auth(request)
    except Exception:
        return _login_redirect()
    return templates.TemplateResponse(request, "app/onboarding.html", {
        "user": user,
        "active": "onboarding",
    })


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    try:
        user_token, user = _auth(request)
    except Exception:
        return _login_redirect()

    profile = db.get_profile(user_token["sub"]) or {}
    return templates.TemplateResponse(request, "app/profile.html", {
        "user": user,
        "profile": profile,
        "active": "profile",
    })


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    try:
        user_token, user = _auth(request)
    except Exception:
        return _login_redirect()

    uid = user_token["sub"]
    settings = db.get_settings(uid)
    profile = db.get_profile(uid) or {}
    default_keywords = ", ".join(profile.get("target_roles", [])) or "QA Analyst, QA Tester, Tester de Software"
    has_credentials = bool(
        settings.get("computrabajo_email") or
        settings.get("bumeran_email") or
        settings.get("zonajobs_email")
    )
    ready = request.query_params.get("ready") == "1"
    return templates.TemplateResponse(request, "app/search.html", {
        "user": user,
        "settings": settings,
        "default_keywords": default_keywords,
        "has_credentials": has_credentials,
        "ready": ready,
        "active": "search",
    })


@router.get("/applications", response_class=HTMLResponse)
async def applications_page(request: Request):
    try:
        user_token, user = _auth(request)
    except Exception:
        return _login_redirect()

    uid = user_token["sub"]
    apps = tracker.get_applications(user_id=uid)
    stats = tracker.get_stats(user_id=uid)
    return templates.TemplateResponse(request, "app/applications.html", {
        "user": user,
        "applications": apps,
        "stats": stats,
        "active": "applications",
    })


@router.get("/upgrade", response_class=HTMLResponse)
async def upgrade_page(request: Request):
    try:
        user_token, user = _auth(request)
    except Exception:
        return _login_redirect()

    runs_used = user.get("runs_used") or 0

    return templates.TemplateResponse(request, "app/upgrade.html", {
        "user": user,
        "runs_used": runs_used,
        "free_runs_limit": FREE_RUNS_LIMIT,
        "mp_checkout_url": os.environ.get("MP_CHECKOUT_URL", "#"),
        "support_whatsapp": os.environ.get("SUPPORT_WHATSAPP", ""),
        "support_email": os.environ.get("SUPPORT_EMAIL", ""),
        "active": "upgrade",
    })


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    try:
        user_token, user = _auth(request)
    except Exception:
        return _login_redirect()

    settings = db.get_settings(user_token["sub"])
    setup = request.query_params.get("setup") == "1"
    return templates.TemplateResponse(request, "app/settings.html", {
        "user": user,
        "settings": settings,
        "setup": setup,
        "active": "settings",
    })
