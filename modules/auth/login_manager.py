"""
Login Manager: maneja autenticación y persistencia de sesión para cada portal.

Flujo:
  1. Intentar cargar cookies guardadas
  2. Si hay cookies, verificar que la sesión sigue activa
  3. Si no hay cookies o expiró, hacer login con email/password
  4. Guardar cookies para la próxima vez
"""
import asyncio
import json
import random
from pathlib import Path
from typing import Optional

from playwright.async_api import BrowserContext, Page

from core import get_logger, settings

logger = get_logger(__name__)

SESSIONS_DIR = Path("data/sessions")


class LoginManager:
    """Gestiona login y cookies para todos los portales."""

    def __init__(self):
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # ─── API pública ──────────────────────────────────────────────────────────

    async def ensure_logged_in(self, context: BrowserContext, portal: str) -> bool:
        """
        Garantiza que el contexto esté autenticado en el portal.
        Retorna True si se logró autenticar, False si no hay credenciales.
        """
        handlers = {
            "computrabajo": self._ensure_computrabajo,
            "bumeran": self._ensure_bumeran,
            "zonajobs": self._ensure_zonajobs,
        }
        handler = handlers.get(portal)
        if not handler:
            logger.warning(f"No hay handler de login para {portal}")
            return False
        return await handler(context)

    def has_credentials(self, portal: str) -> bool:
        creds = {
            "computrabajo": (settings.computrabajo_email, settings.computrabajo_password),
            "bumeran": (settings.bumeran_email, settings.bumeran_password),
            "zonajobs": (settings.zonajobs_email, settings.zonajobs_password),
        }
        email, pwd = creds.get(portal, (None, None))
        return bool(email and pwd)

    # ─── Computrabajo ─────────────────────────────────────────────────────────

    async def _ensure_computrabajo(self, context: BrowserContext) -> bool:
        if not self.has_credentials("computrabajo"):
            logger.warning("Computrabajo: sin credenciales en .env")
            return False

        await self._load_cookies(context, "computrabajo")

        page = await context.new_page()
        try:
            logged_in = await self._check_computrabajo_session(page)
            if logged_in:
                logger.info("Computrabajo: sesión activa (cookies válidas)")
                return True

            logger.info("Computrabajo: iniciando login...")
            success = await self._login_computrabajo(page)
            if success:
                await self._save_cookies(context, "computrabajo")
                logger.info("Computrabajo: login exitoso")
            else:
                logger.error("Computrabajo: login fallido")
            return success
        finally:
            await page.close()

    async def _check_computrabajo_session(self, page: Page) -> bool:
        try:
            await page.goto(
                "https://ar.computrabajo.com/candidato/cv",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(2)
            url = page.url
            return "candidato/cv" in url or "candidato/perfil" in url
        except Exception:
            return False

    async def _login_computrabajo(self, page: Page) -> bool:
        try:
            await page.goto(
                "https://ar.computrabajo.com/candidato/acceso",
                wait_until="domcontentloaded",
            )
            await asyncio.sleep(2)

            await page.fill('input[name="email"], input[type="email"]', settings.computrabajo_email)
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await page.fill('input[name="pass"], input[name="password"], input[type="password"]', settings.computrabajo_password)
            await asyncio.sleep(random.uniform(0.5, 1.0))

            await page.click('button[type="submit"], input[type="submit"]')
            await asyncio.sleep(3)

            url = page.url
            return "candidato" in url and "acceso" not in url
        except Exception as e:
            logger.error(f"Computrabajo login error: {e}")
            return False

    # ─── Bumeran ──────────────────────────────────────────────────────────────

    async def _ensure_bumeran(self, context: BrowserContext) -> bool:
        if not self.has_credentials("bumeran"):
            logger.warning("Bumeran: sin credenciales en .env")
            return False

        await self._load_cookies(context, "bumeran")

        page = await context.new_page()
        try:
            logged_in = await self._check_bumeran_session(page)
            if logged_in:
                logger.info("Bumeran: sesión activa (cookies válidas)")
                return True

            logger.info("Bumeran: iniciando login...")
            success = await self._login_bumeran(page)
            if success:
                await self._save_cookies(context, "bumeran")
                logger.info("Bumeran: login exitoso")
            else:
                logger.error("Bumeran: login fallido")
            return success
        finally:
            await page.close()

    async def _check_bumeran_session(self, page: Page) -> bool:
        try:
            await page.goto(
                "https://www.bumeran.com.ar/postulaciones",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(2)
            url = page.url
            return "postulaciones" in url and "login" not in url
        except Exception:
            return False

    async def _login_bumeran(self, page: Page) -> bool:
        try:
            await page.goto(
                "https://www.bumeran.com.ar/login",
                wait_until="domcontentloaded",
            )
            await asyncio.sleep(2)

            # Bumeran puede tener un botón "Ingresar con email" antes del form
            email_btn = await page.query_selector('button[data-qa="email-login"], a[href*="email"]')
            if email_btn:
                await email_btn.click()
                await asyncio.sleep(1)

            await page.fill('input[type="email"], input[name="email"]', settings.bumeran_email)
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await page.fill('input[type="password"], input[name="password"]', settings.bumeran_password)
            await asyncio.sleep(random.uniform(0.5, 1.0))

            await page.click('button[type="submit"], button[data-qa="login-submit"]')
            await asyncio.sleep(3)

            url = page.url
            return "login" not in url and "bumeran.com.ar" in url
        except Exception as e:
            logger.error(f"Bumeran login error: {e}")
            return False

    # ─── ZonaJobs ─────────────────────────────────────────────────────────────

    async def _ensure_zonajobs(self, context: BrowserContext) -> bool:
        if not self.has_credentials("zonajobs"):
            logger.warning("ZonaJobs: sin credenciales en .env")
            return False

        await self._load_cookies(context, "zonajobs")

        page = await context.new_page()
        try:
            logged_in = await self._check_zonajobs_session(page)
            if logged_in:
                logger.info("ZonaJobs: sesión activa (cookies válidas)")
                return True

            logger.info("ZonaJobs: iniciando login...")
            success = await self._login_zonajobs(page)
            if success:
                await self._save_cookies(context, "zonajobs")
                logger.info("ZonaJobs: login exitoso")
            else:
                logger.error("ZonaJobs: login fallido")
            return success
        finally:
            await page.close()

    async def _check_zonajobs_session(self, page: Page) -> bool:
        try:
            await page.goto(
                "https://www.zonajobs.com.ar/mis-postulaciones",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(2)
            url = page.url
            return "mis-postulaciones" in url and "login" not in url
        except Exception:
            return False

    async def _login_zonajobs(self, page: Page) -> bool:
        try:
            await page.goto(
                "https://www.zonajobs.com.ar/login",
                wait_until="domcontentloaded",
            )
            await asyncio.sleep(2)

            await page.fill('input[type="email"], input[name="email"]', settings.zonajobs_email)
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await page.fill('input[type="password"], input[name="password"]', settings.zonajobs_password)
            await asyncio.sleep(random.uniform(0.5, 1.0))

            await page.click('button[type="submit"]')
            await asyncio.sleep(3)

            url = page.url
            return "login" not in url and "zonajobs.com.ar" in url
        except Exception as e:
            logger.error(f"ZonaJobs login error: {e}")
            return False

    # ─── Cookie persistence ───────────────────────────────────────────────────

    async def _save_cookies(self, context: BrowserContext, portal: str):
        try:
            cookies = await context.cookies()
            path = SESSIONS_DIR / f"{portal}.json"
            path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.debug(f"Cookies guardadas: {portal} ({len(cookies)} cookies)")
        except Exception as e:
            logger.warning(f"No se pudieron guardar cookies de {portal}: {e}")

    async def _load_cookies(self, context: BrowserContext, portal: str):
        path = SESSIONS_DIR / f"{portal}.json"
        if not path.exists():
            return
        try:
            cookies = json.loads(path.read_text(encoding="utf-8"))
            await context.add_cookies(cookies)
            logger.debug(f"Cookies cargadas: {portal} ({len(cookies)} cookies)")
        except Exception as e:
            logger.warning(f"No se pudieron cargar cookies de {portal}: {e}")
