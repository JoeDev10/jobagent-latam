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
    user = get_current_user(request)
    if not user:
        raise Exception("unauth")
    return user


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    try:
        user_token = _auth(request)
    except Exception:
        return RedirectResponse("/login", status_code=302)

    user = db.get_user_by_id(user_token["sub"])
    uid = user_token["sub"]
    stats = tracker.get_stats(user_id=uid)
    recent = tracker.get_applications(user_id=uid)[:10]
    profile = db.get_profile(uid)

    runs_used = user.get("runs_used") or 0 if user else 0

    return templates.TemplateResponse(request, "app/dashboard.html", {
        "user": user,
        "stats": stats,
        "recent_apps": recent,
        "has_profile": profile is not None,
        "runs_used": runs_used,
        "free_runs_limit": FREE_RUNS_LIMIT,
        "active": "dashboard",
    })


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding(request: Request):
    try:
        user_token = _auth(request)
    except Exception:
        return RedirectResponse("/login", status_code=302)
    user = db.get_user_by_id(user_token["sub"])
    return templates.TemplateResponse(request, "app/onboarding.html", {
        "user": user,
        "active": "onboarding",
    })


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    try:
        user_token = _auth(request)
    except Exception:
        return RedirectResponse("/login", status_code=302)

    user = db.get_user_by_id(user_token["sub"])
    profile = db.get_profile(user_token["sub"]) or {}
    return templates.TemplateResponse(request, "app/profile.html", {
        "user": user,
        "profile": profile,
        "active": "profile",
    })


@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    try:
        user_token = _auth(request)
    except Exception:
        return RedirectResponse("/login", status_code=302)

    user = db.get_user_by_id(user_token["sub"])
    settings = db.get_settings(user_token["sub"])
    profile = db.get_profile(user_token["sub"]) or {}
    default_keywords = ", ".join(profile.get("target_roles", [])) or "QA Analyst, QA Tester, Tester de Software"
    return templates.TemplateResponse(request, "app/search.html", {
        "user": user,
        "settings": settings,
        "default_keywords": default_keywords,
        "active": "search",
    })


@router.get("/applications", response_class=HTMLResponse)
async def applications_page(request: Request):
    try:
        user_token = _auth(request)
    except Exception:
        return RedirectResponse("/login", status_code=302)

    user = db.get_user_by_id(user_token["sub"])
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
        user_token = _auth(request)
    except Exception:
        return RedirectResponse("/login", status_code=302)

    user = db.get_user_by_id(user_token["sub"])
    runs_used = user.get("runs_used") or 0 if user else 0

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
        user_token = _auth(request)
    except Exception:
        return RedirectResponse("/login", status_code=302)

    user = db.get_user_by_id(user_token["sub"])
    settings = db.get_settings(user_token["sub"])
    return templates.TemplateResponse(request, "app/settings.html", {
        "user": user,
        "settings": settings,
        "active": "settings",
    })
