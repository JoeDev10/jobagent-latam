"""
FastAPI app principal del SaaS JobAgent LATAM.
"""
import sys
from pathlib import Path

# Asegurar que el directorio raíz del proyecto esté en sys.path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from web import db
from web.templates_env import templates
from web.routers import auth_router, app_router, api_router

# Inicializar DB de usuarios
db.init_db()

app = FastAPI(title="JobAgent LATAM", docs_url=None, redoc_url=None)

# Static files
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Routers
app.include_router(auth_router.router)
app.include_router(app_router.router)
app.include_router(api_router.router)


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    from web.auth import get_current_user
    user = get_current_user(request)
    return templates.TemplateResponse(request, "landing.html", {"user": user})


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return RedirectResponse("/", status_code=302)
