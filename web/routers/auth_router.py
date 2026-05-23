from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from web.auth import create_token, verify_password, hash_password, get_current_user
from web.templates_env import templates
from web import db

router = APIRouter()


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
    token = create_token(uid, email)
    response = RedirectResponse("/app/onboarding", status_code=302)
    response.set_cookie("session", token, httponly=True, max_age=60 * 60 * 24 * 30, samesite="lax")
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("session")
    return response
