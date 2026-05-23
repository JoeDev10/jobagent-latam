"""
Admin UI — panel de administración protegido con clave.
Rutas:
  GET  /admin          → redirect a /admin/login
  GET  /admin/login    → formulario de login
  POST /admin/login    → valida clave, setea cookie admin_session
  GET  /admin/panel    → panel con lista de usuarios
  GET  /admin/logout   → borra cookie y redirige
"""
import hmac
import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from web import db
from web.templates_env import templates

router = APIRouter(prefix="/admin")

_COOKIE = "admin_session"


def _is_admin(request: Request) -> bool:
    secret = os.environ.get("ADMIN_SECRET", "")
    if not secret:
        return False
    cookie = request.cookies.get(_COOKIE, "")
    return bool(cookie) and hmac.compare_digest(cookie.encode(), secret.encode())


@router.get("", response_class=HTMLResponse)
async def admin_root():
    return RedirectResponse("/admin/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    if _is_admin(request):
        return RedirectResponse("/admin/panel", status_code=302)
    return templates.TemplateResponse(request, "admin/login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
async def admin_login_submit(request: Request, secret: str = Form(...)):
    admin_secret = os.environ.get("ADMIN_SECRET", "")
    if not admin_secret or not hmac.compare_digest(secret.encode(), admin_secret.encode()):
        return templates.TemplateResponse(
            request, "admin/login.html",
            {"error": "Clave incorrecta"},
            status_code=401,
        )
    response = RedirectResponse("/admin/panel", status_code=302)
    response.set_cookie(_COOKIE, admin_secret, httponly=True, max_age=60 * 60 * 8, samesite="lax")
    return response


@router.get("/panel", response_class=HTMLResponse)
async def admin_panel(request: Request):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    users = db.get_all_users()
    total = len(users)
    pro = sum(1 for u in users if u.get("plan") == "pro")
    return templates.TemplateResponse(request, "admin/panel.html", {
        "users": users,
        "total_users": total,
        "pro_users": pro,
        "free_users": total - pro,
        "admin_secret": os.environ.get("ADMIN_SECRET", ""),
    })


@router.get("/logout")
async def admin_logout():
    response = RedirectResponse("/admin/login", status_code=302)
    response.delete_cookie(_COOKIE)
    return response
