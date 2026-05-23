"""
FastAPI app principal del SaaS VacantIA.
"""
import sys
from pathlib import Path

# Asegurar que el directorio raíz del proyecto esté en sys.path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from web import db
from web.templates_env import templates
from web.routers import auth_router, app_router, api_router, admin_router

# Inicializar DB de usuarios
db.init_db()

app = FastAPI(title="VacantIA", docs_url=None, redoc_url=None)

# Static files
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Routers
app.include_router(auth_router.router)
app.include_router(app_router.router)
app.include_router(api_router.router)
app.include_router(admin_router.router)


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    from web.auth import get_current_user
    user = get_current_user(request)
    user_count = db.get_user_count()
    return templates.TemplateResponse(request, "landing.html", {"user": user, "user_count": user_count})


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse(request, "privacy.html", {})


@app.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return templates.TemplateResponse(request, "terms.html", {})


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /app/\n"
        "Disallow: /admin/\n"
        "Disallow: /api/\n"
        "Sitemap: https://jobagent-latam.onrender.com/sitemap.xml\n"
    )


@app.get("/sitemap.xml", response_class=PlainTextResponse)
async def sitemap():
    base = "https://jobagent-latam.onrender.com"
    urls = ["", "/privacy", "/terms"]
    items = "\n".join(
        f"  <url><loc>{base}{u}</loc><changefreq>monthly</changefreq></url>"
        for u in urls
    )
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{items}\n</urlset>'


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse(request, "404.html", {}, status_code=404)
