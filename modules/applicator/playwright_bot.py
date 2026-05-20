"""
Bot de aplicación automática con login integrado.

Flujo para cada vacante:
  1. Asegurar sesión activa (login si es necesario)
  2. Navegar a la URL de la vacante
  3. Hacer clic en el botón de aplicación
  4. Completar carta de presentación si hay campo
  5. Confirmar y verificar éxito
"""
import asyncio
import uuid
from datetime import datetime

from playwright.async_api import Page

from core import Application, ApplicationStatus, JobListing, Portal, UserProfile, get_logger
from modules.auth import LoginManager
from modules.scrapers.base import BaseScraper

logger = get_logger(__name__)


class ApplicationBot(BaseScraper):
    """Bot que aplica automáticamente a vacantes en los distintos portales."""

    def __init__(self):
        super().__init__()
        self.login_manager = LoginManager()
        self._logged_in: set[str] = set()  # portales ya autenticados esta sesión

    async def apply(self, application: Application) -> Application:
        portal = application.job.portal
        strategies = {
            Portal.COMPUTRABAJO: self._apply_computrabajo,
            Portal.BUMERAN: self._apply_bumeran,
            Portal.INDEED: self._apply_indeed,
            Portal.ZONAJOBS: self._apply_zonajobs,
        }

        strategy = strategies.get(portal)
        if not strategy:
            logger.warning(f"No hay estrategia de aplicación para {portal}")
            application.status = ApplicationStatus.PENDING
            application.notes = f"Portal {portal.value} no soportado aún"
            return application

        try:
            # Login antes de aplicar (solo una vez por portal por sesión)
            if portal.value not in self._logged_in:
                logged_in = await self.login_manager.ensure_logged_in(self.context, portal.value)
                if logged_in:
                    self._logged_in.add(portal.value)
                else:
                    logger.warning(f"Sin sesión en {portal.value} — aplicación sin login")

            application = await strategy(application)
        except Exception as e:
            logger.error(f"Error aplicando a {application.job.title}: {e}")
            application.status = ApplicationStatus.PENDING
            application.notes = f"Error: {str(e)[:200]}"

        return application

    # ─── Computrabajo ─────────────────────────────────────────────────────────

    async def _apply_computrabajo(self, application: Application) -> Application:
        page = await self.new_page()
        try:
            await page.goto(application.job.url, wait_until="domcontentloaded")
            await self.human_delay(2, 3)

            # Buscar botón de inscripción (varios selectores posibles)
            apply_btn = await page.query_selector(
                'a.applyBtn, button.applyBtn, '
                'a[data-testid="apply-button"], '
                'a.js-inscribirse, button.js-inscribirse, '
                'a[href*="inscribirse"], button[class*="inscri"]'
            )

            if not apply_btn:
                application.status = ApplicationStatus.PENDING
                application.notes = "No se encontró botón de aplicación en Computrabajo"
                return application

            await apply_btn.click()
            await self.human_delay(2, 4)

            # Puede aparecer modal o redirigir a página de confirmación
            # Buscar campo de carta de presentación
            cover_letter_field = await page.query_selector(
                'textarea[name="carta"], textarea[placeholder*="presentaci"], '
                'textarea[id*="cover"], textarea[name*="message"], textarea[name*="carta"]'
            )
            if cover_letter_field and application.cover_letter:
                letter = application.cover_letter[:2000]
                await cover_letter_field.fill(letter)
                await self.human_delay(0.5, 1.5)

            # Botón de confirmar
            confirm_btn = await page.query_selector(
                'button[type="submit"], button.btn-primary, '
                'input[type="submit"], button[class*="confirm"]'
            )
            if confirm_btn:
                await confirm_btn.click()
                await self.human_delay(2, 4)

                # Verificar éxito — Computrabajo muestra mensaje o redirige
                success_selectors = [
                    '.success', '.alert-success', '[class*="success"]',
                    '[class*="inscripto"]', '[class*="postulado"]',
                    'p:has-text("inscripto")', 'div:has-text("postulación enviada")',
                ]
                success = None
                for sel in success_selectors:
                    try:
                        success = await page.query_selector(sel)
                        if success:
                            break
                    except Exception:
                        pass

                # También chequeamos URL (Computrabajo a veces redirige a confirmación)
                current_url = page.url
                if success or "confirmacion" in current_url or "gracias" in current_url:
                    application.status = ApplicationStatus.APPLIED
                    application.applied_at = datetime.now()
                    logger.info(f"[Computrabajo] Aplicado: {application.job.title} @ {application.job.company}")
                else:
                    application.status = ApplicationStatus.PENDING
                    application.notes = "No se pudo confirmar la aplicación (revisar manualmente)"
            else:
                application.status = ApplicationStatus.PENDING
                application.notes = "No se encontró botón de confirmación"

        finally:
            await page.close()
        return application

    # ─── Bumeran ──────────────────────────────────────────────────────────────

    async def _apply_bumeran(self, application: Application) -> Application:
        page = await self.new_page()
        try:
            await page.goto(application.job.url, wait_until="domcontentloaded")
            await self.human_delay(2, 3)

            apply_btn = await page.query_selector(
                'button[data-qa="btn-apply"], a[data-qa="btn-apply"], '
                'button.apply-button, a.apply-button, '
                'button[class*="postular"], a[class*="postular"]'
            )

            if not apply_btn:
                application.status = ApplicationStatus.PENDING
                application.notes = "No se encontró botón de aplicación en Bumeran"
                return application

            await apply_btn.click()
            await self.human_delay(2, 4)

            # Carta de presentación
            cover_field = await page.query_selector(
                'textarea[name*="cover"], textarea[placeholder*="presentaci"], '
                'textarea[data-qa*="cover"], textarea[class*="cover"]'
            )
            if cover_field and application.cover_letter:
                await cover_field.fill(application.cover_letter[:2000])
                await self.human_delay(1, 2)

            submit = await page.query_selector(
                'button[type="submit"], button[data-qa="submit"], '
                'button[class*="submit"], button[class*="postular"]'
            )
            if submit:
                await submit.click()
                await self.human_delay(2, 4)

                # Verificar éxito
                current_url = page.url
                success = await page.query_selector(
                    '[class*="success"], [class*="postulado"], '
                    '[data-qa*="success"], .postulation-success'
                )
                if success or "postulaciones" in current_url or "gracias" in current_url:
                    application.status = ApplicationStatus.APPLIED
                    application.applied_at = datetime.now()
                    logger.info(f"[Bumeran] Aplicado: {application.job.title} @ {application.job.company}")
                else:
                    application.status = ApplicationStatus.PENDING
                    application.notes = "No se pudo confirmar la aplicación en Bumeran"
            else:
                application.status = ApplicationStatus.PENDING
                application.notes = "No se encontró botón de confirmación en Bumeran"

        finally:
            await page.close()
        return application

    # ─── ZonaJobs ─────────────────────────────────────────────────────────────

    async def _apply_zonajobs(self, application: Application) -> Application:
        page = await self.new_page()
        try:
            await page.goto(application.job.url, wait_until="domcontentloaded")
            await self.human_delay(2, 3)

            apply_btn = await page.query_selector(
                'button[class*="postular"], a[class*="postular"], '
                'button[class*="apply"], a[class*="apply"], '
                'button[data-qa*="apply"], a[data-qa*="apply"]'
            )

            if not apply_btn:
                application.status = ApplicationStatus.PENDING
                application.notes = "No se encontró botón de aplicación en ZonaJobs"
                return application

            await apply_btn.click()
            await self.human_delay(2, 4)

            # Carta de presentación
            cover_field = await page.query_selector('textarea[name*="cover"], textarea[placeholder*="presentaci"]')
            if cover_field and application.cover_letter:
                await cover_field.fill(application.cover_letter[:2000])
                await self.human_delay(1, 2)

            submit = await page.query_selector('button[type="submit"], button[class*="postular"]')
            if submit:
                await submit.click()
                await self.human_delay(2, 4)

                success = await page.query_selector('[class*="success"], [class*="postulado"]')
                current_url = page.url
                if success or "postulaciones" in current_url:
                    application.status = ApplicationStatus.APPLIED
                    application.applied_at = datetime.now()
                    logger.info(f"[ZonaJobs] Aplicado: {application.job.title} @ {application.job.company}")
                else:
                    application.status = ApplicationStatus.PENDING
                    application.notes = "No se pudo confirmar la aplicación en ZonaJobs"
            else:
                application.status = ApplicationStatus.PENDING
                application.notes = "No se encontró botón de confirmación en ZonaJobs"

        finally:
            await page.close()
        return application

    # ─── Indeed ───────────────────────────────────────────────────────────────

    async def _apply_indeed(self, application: Application) -> Application:
        # Indeed usa un flujo complejo con preguntas personalizadas por empresa.
        # Lo marcamos como pendiente para revisión manual.
        application.status = ApplicationStatus.PENDING
        application.notes = "Indeed: aplicar manualmente (flujo variable por empresa)"
        return application

    # ─── BaseScraper stubs ────────────────────────────────────────────────────

    async def search(self, config):
        raise NotImplementedError

    async def get_job_detail(self, url: str):
        raise NotImplementedError
