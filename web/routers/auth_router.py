import os
import secrets
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from web.auth import create_token, verify_password, hash_password, get_current_user
from web.templates_env import templates
from web import db

router = APIRouter()


async def _send_reset_email(to_email: str, reset_link: str):
    """Envía email de reset vía Resend si RESEND_API_KEY está configurado."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        return
    from_addr = os.environ.get("RESEND_FROM", "JobAgent LATAM <noreply@jobagentlatam.com>")
    html = (
        f"<p>Hola,</p>"
        f"<p>Recibimos una solicitud para restablecer la contraseña de tu cuenta en JobAgent LATAM.</p>"
        f"<p><a href='{reset_link}' style='background:#7c3aed;color:#fff;padding:12px 24px;"
        f"border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block'>"
        f"Restablecer contraseña</a></p>"
        f"<p>Este enlace vence en 2 horas. Si no solicitaste este cambio, ignorá este email.</p>"
        f"<p>— Equipo JobAgent LATAM</p>"
    )
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": from_addr, "to": [to_email], "subject": "Restablecé tu contraseña — JobAgent LATAM", "html": html},
            )
    except Exception:
        pass


async def _notify_telegram_new_user(full_name: str, email: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    text = f"🆕 Nuevo usuario registrado\n👤 {full_name}\n📧 {email}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
    except Exception:
        pass


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/app/dashboard", status_code=302)
    return templates.TemplateResponse(request, "auth/login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    user = db.get_user_by_email(email)
    if not user or not verify_password(password, user["password"]):
        return templates.TemplateResponse(
            request, "auth/login.html",
            {"error": "Email o contraseña incorrectos"},
            status_code=401,
        )
    db.update_last_login(user["id"])
    token = create_token(user["id"], user["email"])
    response = RedirectResponse("/app/dashboard", status_code=302)
    response.set_cookie("session", token, httponly=True, max_age=60 * 60 * 24 * 30, samesite="lax")
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/app/dashboard", status_code=302)
    return templates.TemplateResponse(request, "auth/register.html", {"error": None})


@router.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    background_tasks: BackgroundTasks,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    if password != password2:
        return templates.TemplateResponse(
            request, "auth/register.html",
            {"error": "Las contraseñas no coinciden"},
            status_code=400,
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            request, "auth/register.html",
            {"error": "La contraseña debe tener al menos 8 caracteres"},
            status_code=400,
        )
    uid = db.create_user(email, hash_password(password), full_name)
    if uid is None:
        return templates.TemplateResponse(
            request, "auth/register.html",
            {"error": "Ese email ya está registrado"},
            status_code=400,
        )
    background_tasks.add_task(_notify_telegram_new_user, full_name, email)
    token = create_token(uid, email)
    response = RedirectResponse("/app/onboarding", status_code=302)
    response.set_cookie("session", token, httponly=True, max_age=60 * 60 * 24 * 30, samesite="lax")
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("session")
    return response


# ─── Forgot password ──────────────────────────────────────────────────────────

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "auth/forgot_password.html", {"sent": False, "error": None})


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_submit(request: Request, email: str = Form(...)):
    user = db.get_user_by_email(email)
    if user:
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now() + timedelta(hours=2)).isoformat()
        db.create_reset_token(user["id"], token, expires_at)
        app_url = os.environ.get("APP_URL", "http://localhost:8000")
        reset_link = f"{app_url}/reset-password?token={token}"
        # Send via Resend if configured (production), Telegram as fallback (dev)
        await _send_reset_email(user["email"], reset_link)
        tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
        if tg_token and tg_chat:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(
                        f"https://api.telegram.org/bot{tg_token}/sendMessage",
                        json={"chat_id": tg_chat, "text": f"Reset password link para {email}:\n{reset_link}"},
                    )
            except Exception:
                pass
    return templates.TemplateResponse(request, "auth/forgot_password.html", {"sent": True, "error": None})


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str = ""):
    record = db.get_reset_token(token) if token else None
    if not record:
        return templates.TemplateResponse(request, "auth/reset_password.html",
                                          {"valid": False, "token": token, "done": False})
    expired = datetime.fromisoformat(record["expires_at"]) < datetime.now()
    return templates.TemplateResponse(request, "auth/reset_password.html",
                                      {"valid": not expired, "token": token, "done": False})


@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password_submit(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    record = db.get_reset_token(token)
    if not record or datetime.fromisoformat(record["expires_at"]) < datetime.now():
        return templates.TemplateResponse(request, "auth/reset_password.html",
                                          {"valid": False, "token": token, "done": False})
    if password != password2:
        return templates.TemplateResponse(request, "auth/reset_password.html",
                                          {"valid": True, "token": token, "done": False,
                                           "error": "Las contraseñas no coinciden"})
    if len(password) < 8:
        return templates.TemplateResponse(request, "auth/reset_password.html",
                                          {"valid": True, "token": token, "done": False,
                                           "error": "Mínimo 8 caracteres"})
    db.update_password(record["user_id"], hash_password(password))
    db.mark_token_used(token)
    return templates.TemplateResponse(request, "auth/reset_password.html",
                                      {"valid": True, "token": token, "done": True})
