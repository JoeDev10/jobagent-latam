"""
Lee las cookies del Chrome real del usuario y las convierte al formato
de Playwright. No requiere abrir ningún navegador.

Estrategia:
1. Intenta leer cookies de Chrome (perfil Default)
2. Fallback a Edge, Firefox
3. Si Chrome está abierto y bloquea la DB, copia el archivo a temp primero
4. Devuelve lista de cookies en formato Playwright

Esto evita toda la detección de anti-bots porque las cookies vienen de un
navegador real con sesión real.
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from core import get_logger

logger = get_logger(__name__)

# Dominios para los que leemos cookies
DOMAIN_FILTERS = {
    "computrabajo": [".computrabajo.com", "computrabajo.com",
                     ".ar.computrabajo.com", "ar.computrabajo.com",
                     "secure.computrabajo.com", "candidato.ar.computrabajo.com"],
    "bumeran":      [".bumeran.com.ar", "bumeran.com.ar",
                     "www.bumeran.com.ar"],
    "zonajobs":     [".zonajobs.com.ar", "zonajobs.com.ar", "www.zonajobs.com.ar"],
}


def _to_playwright_cookie(c) -> dict:
    """Convierte una cookie de http.cookiejar al formato Playwright."""
    # browser_cookie3 devuelve http.cookiejar.Cookie objects
    cookie = {
        "name": c.name,
        "value": c.value,
        "domain": c.domain,
        "path": c.path or "/",
        "secure": bool(c.secure),
        # httpOnly y sameSite a veces no están disponibles
    }
    if c.expires:
        cookie["expires"] = float(c.expires)
    # Detectar httpOnly desde rest
    rest = getattr(c, "_rest", {}) or {}
    if "HttpOnly" in rest or "httponly" in {k.lower() for k in rest}:
        cookie["httpOnly"] = True
    return cookie


def _filter_cookies(cookies, domain_patterns: list[str]) -> list[dict]:
    """Filtra cookies que coincidan con alguno de los dominios y conviértelas."""
    out = []
    for c in cookies:
        if not c.value:
            continue
        domain = c.domain or ""
        # Match flexible: cualquiera de los patrones que aparezca en el dominio
        if any(p.lstrip(".") in domain for p in domain_patterns):
            try:
                out.append(_to_playwright_cookie(c))
            except Exception as e:
                logger.debug(f"No se pudo convertir cookie {c.name}: {e}")
    return out


def _try_load_chrome() -> Optional[list]:
    """Intenta leer cookies de Chrome. Si el archivo está bloqueado, lo copia
    a un temp y reintenta."""
    try:
        import browser_cookie3
        try:
            return list(browser_cookie3.chrome())
        except (PermissionError, Exception) as e:
            logger.warning(f"Chrome cookies bloqueadas, intento workaround: {e}")
            return _try_chrome_via_temp_copy()
    except ImportError:
        logger.error("browser_cookie3 no instalado")
        return None


def _try_chrome_via_temp_copy() -> Optional[list]:
    """Copia la DB de cookies de Chrome a un temp y la lee desde ahí.
    Funciona aunque Chrome esté abierto."""
    try:
        import os
        import browser_cookie3

        # Encontrar el archivo de cookies de Chrome
        local = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            Path(local) / "Google" / "Chrome" / "User Data" / "Default" / "Network" / "Cookies",
            Path(local) / "Google" / "Chrome" / "User Data" / "Default" / "Cookies",
        ]
        src = next((p for p in candidates if p.exists()), None)
        if not src:
            logger.warning("No encontré el archivo de Cookies de Chrome")
            return None

        # Copiar a temp
        tmp = Path(tempfile.gettempdir()) / f"chrome_cookies_{datetime.now().timestamp()}.db"
        shutil.copy2(src, tmp)
        try:
            cookies = list(browser_cookie3.chrome(cookie_file=str(tmp)))
            logger.info(f"Cookies leídas vía copia temporal ({len(cookies)} totales)")
            return cookies
        finally:
            try:
                tmp.unlink()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Falló copia temporal de cookies de Chrome: {e}")
        return None


def _try_load_browser(name: str) -> Optional[list]:
    """Intenta leer cookies de Edge, Firefox, Brave."""
    try:
        import browser_cookie3
        fn = {
            "edge": browser_cookie3.edge,
            "firefox": browser_cookie3.firefox,
            "brave": browser_cookie3.brave,
        }.get(name)
        if not fn:
            return None
        return list(fn())
    except Exception as e:
        logger.debug(f"No pude leer {name}: {e}")
        return None


def load_cookies_for_portal(portal: str) -> list[dict]:
    """
    Carga cookies del navegador real (Chrome → Edge → Firefox → Brave)
    para el portal especificado.

    Devuelve lista en formato Playwright. Vacía si no se encontró nada.
    """
    portal = portal.lower()
    if portal not in DOMAIN_FILTERS:
        logger.warning(f"Portal '{portal}' no tiene filtros de dominio definidos")
        return []

    patterns = DOMAIN_FILTERS[portal]

    for browser_name, loader in [
        ("chrome", _try_load_chrome),
        ("edge", lambda: _try_load_browser("edge")),
        ("brave", lambda: _try_load_browser("brave")),
        ("firefox", lambda: _try_load_browser("firefox")),
    ]:
        raw = loader()
        if not raw:
            continue
        filtered = _filter_cookies(raw, patterns)
        if filtered:
            logger.info(f"[{portal}] {len(filtered)} cookies cargadas desde {browser_name}")
            return filtered
        else:
            logger.debug(f"[{portal}] {browser_name} tiene cookies pero ninguna del dominio")

    logger.warning(
        f"[{portal}] No se encontraron cookies en ningún navegador. "
        f"Andá a {portal} en tu navegador, logueate, y volvé a correr el bot."
    )
    return []


def has_auth_cookies(cookies: list[dict], portal: str) -> bool:
    """
    Heurística: ¿estas cookies parecen incluir una sesión autenticada?
    Buscamos nombres comunes de cookies de auth de ASP.NET, OAuth, etc.
    """
    AUTH_PATTERNS = [
        ".aspnetcore.identity", ".aspnet.applicationcookie",
        ".aspxauth", "aspxauth", "idsrv", "idsrv.session",
        "auth_token", "access_token", "id_token", "remember",
        ".aspnetcore.cookies",
    ]
    for c in cookies:
        name = c["name"].lower()
        if any(p in name for p in AUTH_PATTERNS):
            return True
    return False
