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

SESSIONS_DIR = Path(__file__).parent.parent.parent / "data" / "sessions"


class LoginManager:
    """Gestiona login y cookies para todos los portales."""

    def __init__(self):
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # ─── API pública ──────────────────────────────────────────────────────────

    async def ensure_logged_in(self, context: BrowserContext, portal: str) -> bool:
        """
        Garantiza que el contexto esté autenticado en el portal.

        Estrategia (en orden de preferencia):
        1. Cargar cookies del Chrome real del usuario (browser_cookie3)
           — INVISIBLE al anti-bot porque las cookies vienen de un Chrome real.
        2. Cargar cookies guardadas en disco (data/sessions/<portal>.json)
           de sesiones anteriores del bot.
        3. Login automatizado con email/password del .env (fallback frágil).
        """
        # Paso 1: intentar leer cookies del Chrome del usuario
        try:
            from .cookie_loader import load_cookies_for_portal, has_auth_cookies
            real_cookies = load_cookies_for_portal(portal)
            if real_cookies:
                await context.add_cookies(real_cookies)
                # Persistir para sesiones futuras
                await self._save_cookies(context, portal)
                logger.info(f"[{portal}] {len(real_cookies)} cookies cargadas desde Chrome real")
                # Verificar si parecen tener auth
                if has_auth_cookies(real_cookies, portal):
                    logger.info(f"[{portal}] cookies tienen señales de autenticación ✓")
                    return True
                else:
                    logger.warning(
                        f"[{portal}] cookies cargadas pero sin tokens de auth obvios — "
                        f"voy a verificar contra el sitio"
                    )
                    # Continuamos al verify para chequear si igual funciona
        except Exception as e:
            logger.warning(f"[{portal}] No pude leer cookies del navegador real: {e}")

        # Paso 2 y 3: handler clásico (cookies en disco + login automatizado)
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
        """
        Verifica sesión activa.
        Estrategia: ir a /candidato/cv y confirmar que la página contiene
        elementos visibles sólo cuando estás logueado (link 'Cerrar sesión'
        o nombre de usuario en el header). El simple chequeo de URL no es
        confiable porque Computrabajo a veces no redirige aun sin sesión.
        """
        try:
            await page.goto(
                "https://ar.computrabajo.com/candidato/cv",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await asyncio.sleep(2)

            # Si la URL contiene 'acceso' o 'login', claramente no hay sesión
            url = page.url.lower()
            if "acceso" in url or "login" in url or "iniciar-sesion" in url:
                return False

            # Buscar evidencia concreta de estar logueado
            evidence = await page.evaluate("""
                () => {
                    const t = (document.body.innerText || '').toLowerCase();
                    return {
                        has_logout: /cerrar\\s*sesi[oó]n|salir/.test(t),
                        has_my_account: /mi\\s*cuenta|mis\\s*postulaciones|mi\\s*perfil/.test(t),
                        has_login_link: /iniciar\\s*sesi[oó]n|^ingresar$/m.test(t),
                    };
                }
            """)
            # Logueado si vemos opciones de cuenta y NO el link de iniciar sesión
            return (evidence["has_logout"] or evidence["has_my_account"]) and not evidence["has_login_link"]
        except Exception:
            return False

    async def _login_computrabajo(self, page: Page) -> bool:
        """
        Login en Computrabajo (flujo 2026):
        Migró a OAuth en secure.computrabajo.com. Hay que entrar vía el link
        'Iniciar sesión' del home, no directo a /Account/Login (redirige sin
        el contexto OAuth correcto).
        """
        try:
            # 1. Ir al home
            await page.goto(
                "https://ar.computrabajo.com/",
                wait_until="domcontentloaded",
            )
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            await asyncio.sleep(1)

            # 2. Click en 'Iniciar sesión' / 'Ingresar'
            iniciar_clicked = False
            for sel in [
                'a:has-text("Iniciar sesión")',
                'a:has-text("Iniciar Sesión")',
                'a:has-text("Ingresar")',
                'button:has-text("Iniciar sesión")',
                'a[href*="acceso"]',
                'a[href*="login"]',
                'a[href*="Account/Login"]',
            ]:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click()
                        iniciar_clicked = True
                        logger.info(f"Computrabajo: click en login con {sel}")
                        break
                except Exception:
                    continue

            if not iniciar_clicked:
                logger.error("Computrabajo: no encontré link 'Iniciar sesión' en home")
                return False

            # 3. Esperar la página de login
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await asyncio.sleep(2)

            # Esperar el campo de email
            try:
                await page.wait_for_selector('input[name="Email"], input#Email', timeout=15000)
            except Exception:
                logger.error(f"Computrabajo: no apareció el campo Email (URL: {page.url})")
                return False

            # Llenar email (case-sensitive: name="Email" con E mayúscula)
            await page.fill('input[name="Email"], input#Email', settings.computrabajo_email)
            await asyncio.sleep(random.uniform(0.5, 1.2))

            # Llenar contraseña
            await page.fill('input[name="Password"], input#password', settings.computrabajo_password)
            await asyncio.sleep(random.uniform(0.5, 1.2))

            # Click en Continuar
            clicked = False
            for sel in [
                'button:has-text("Continuar")',
                'button[type="submit"]',
                'input[type="submit"]',
            ]:
                try:
                    btn = await page.query_selector(sel)
                    if btn:
                        await btn.click()
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                logger.error("Computrabajo: no se encontró botón Continuar")
                return False

            # Esperar redirect post-login
            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            await asyncio.sleep(3)

            url = page.url.lower()
            # Éxito si NO seguimos en /Account/Login
            ok = "account/login" not in url
            if not ok:
                logger.warning(f"Computrabajo: URL post-login inesperada: {page.url}")
            return ok
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
