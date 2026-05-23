"""
Bot de aplicación automática con login integrado.

Flujo para cada vacante:
  1. Asegurar sesión activa (login si es necesario)
  2. Navegar a la URL de la vacante
  3. Hacer clic en el botón de aplicación
  4. Detectar flujo post-click:
     a) Aplicación directa → confirmar éxito
     b) Preguntas de selección → responder con IA → enviar
  5. Verificar resultado
"""
import asyncio
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from groq import AsyncGroq
from playwright.async_api import Page

from core import Application, ApplicationStatus, JobListing, Portal, UserProfile, get_logger, settings
from modules.auth import LoginManager
from modules.profile import ProfileManager
from modules.scrapers.base import BaseScraper

SCREENSHOTS_DIR = Path(__file__).parent.parent.parent / "data" / "screenshots"

logger = get_logger(__name__)


class ApplicationBot(BaseScraper):
    """Bot que aplica automáticamente a vacantes en los distintos portales."""

    def __init__(self, cdp_url: str | None = None):
        super().__init__(cdp_url=cdp_url)
        self.login_manager = LoginManager()
        self._logged_in: set[str] = set()
        self._groq = AsyncGroq(api_key=settings.groq_api_key)
        self._profile_manager = ProfileManager()
        if self.cdp_url:
            self._logged_in.update({"computrabajo", "bumeran", "zonajobs"})

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

            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            await self.human_delay(2, 3)

            # 1. Buscar botón "Postularme"
            apply_btn = None
            selectors = [
                'a.b_primary:has-text("Postularme")',
                'a.b_primary:has-text("Postular")',
                'a.b_primary:has-text("Inscribirme")',
                'button.b_primary:has-text("Postularme")',
                'a:has-text("Postularme")',
                'button:has-text("Postularme")',
            ]
            for sel in selectors:
                try:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        apply_btn = btn
                        logger.info(f"[Computrabajo] Botón encontrado con: {sel}")
                        break
                except Exception:
                    continue

            if not apply_btn:
                # Verificar si ya se aplicó previamente
                body_check = await page.evaluate(
                    "() => (document.body.innerText || '').slice(0, 5000).toLowerCase()"
                )
                if "ya aplicaste" in body_check or "postulado" in body_check:
                    application.status = ApplicationStatus.APPLIED
                    application.applied_at = datetime.now()
                    logger.info(f"[Computrabajo] Ya aplicado previamente: {application.job.title}")
                    return application
                application.status = ApplicationStatus.PENDING
                application.notes = "No se encontró botón de aplicación en Computrabajo"
                await self._screenshot_failure(page, application)
                return application

            await apply_btn.click()
            await self.human_delay(3, 5)

            # 2. Detectar qué flujo apareció post-click
            body_text = await page.evaluate(
                "() => (document.body.innerText || '').slice(0, 5000).toLowerCase()"
            )

            if "preguntas de selecci" in body_text:
                # ── Flujo B: preguntas de selección ──
                logger.info("[Computrabajo] Detectado: Preguntas de selección")
                answered = await self._answer_screening_questions(page, application)
                if not answered:
                    application.status = ApplicationStatus.PENDING
                    application.notes = "No se pudieron responder las preguntas de selección"
                    await self._screenshot_failure(page, application)
                    return application

                # Scroll al fondo y buscar "Enviar mi CV"
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await self.human_delay(1, 2)

                clicked_send = await page.evaluate("""
                    () => {
                        const candidates = [...document.querySelectorAll('button, a, input[type="submit"]')];
                        const btn = candidates.find(el => {
                            const t = (el.innerText || el.value || '').toLowerCase();
                            return t.includes('enviar mi cv') || t.includes('enviar cv') || t.includes('enviar');
                        });
                        if (btn) {
                            btn.scrollIntoView({behavior: 'smooth', block: 'center'});
                            setTimeout(() => btn.click(), 500);
                            return true;
                        }
                        return false;
                    }
                """)
                if clicked_send:
                    await self.human_delay(3, 5)
                else:
                    application.status = ApplicationStatus.PENDING
                    application.notes = "No se encontró botón 'Enviar mi CV'"
                    await self._screenshot_failure(page, application)
                    return application

                # Verificar éxito post-envío
                post_body = await page.evaluate(
                    "() => (document.body.innerText || '').slice(0, 5000).toLowerCase()"
                )
                if any(s in post_body for s in [
                    "adjuntado", "postulaci", "candidatura", "hemos recibido",
                    "carta de presentaci", "ofertas similares",
                ]):
                    application.status = ApplicationStatus.APPLIED
                    application.applied_at = datetime.now()
                    logger.info(f"[Computrabajo] Aplicado (con preguntas): {application.job.title}")
                else:
                    application.status = ApplicationStatus.PENDING
                    application.notes = "Preguntas respondidas pero no se pudo confirmar envío"
                    await self._screenshot_failure(page, application)

            elif any(s in body_text for s in [
                "adjuntado", "hemos adjuntado", "postulaci",
                "carta de presentaci", "ofertas similares",
            ]):
                # ── Flujo A: aplicación directa (ya se envió al hacer click) ──
                application.status = ApplicationStatus.APPLIED
                application.applied_at = datetime.now()
                logger.info(f"[Computrabajo] Aplicado (directo): {application.job.title}")

            else:
                application.status = ApplicationStatus.PENDING
                application.notes = "Flujo post-click no reconocido"
                await self._screenshot_failure(page, application)

        finally:
            await page.close()
        return application

    async def _answer_screening_questions(self, page: Page, application: Application) -> bool:
        """Extrae preguntas de selección de Computrabajo y las responde con IA."""
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self.human_delay(1, 2)
            await page.evaluate("window.scrollTo(0, 0)")
            await self.human_delay(0.5, 1)

            questions_data = await page.evaluate("""
                () => {
                    const questions = [];
                    const seenNames = new Set();

                    // Agrupar radios por name (KillerQuestions[N].ClosedQuestion)
                    const allRadios = document.querySelectorAll('input[type="radio"]');
                    const radioGroups = {};
                    allRadios.forEach(inp => {
                        const name = inp.name;
                        if (!radioGroups[name]) radioGroups[name] = [];
                        radioGroups[name].push(inp);
                    });

                    for (const [name, radios] of Object.entries(radioGroups)) {
                        if (seenNames.has(name)) continue;
                        seenNames.add(name);

                        // Buscar el texto de la pregunta: subir desde el grupo de radios
                        const container = radios[0].closest('.field_radio_box, .question, [class*="killer"]')
                            || radios[0].closest('div')?.parentElement
                            || radios[0].parentElement?.parentElement?.parentElement;
                        let questionText = '';
                        if (container) {
                            const label = container.previousElementSibling
                                || container.parentElement?.querySelector('b, strong, h3, h4, p > b');
                            questionText = label ? label.innerText.trim() : '';
                        }
                        // Fallback: buscar el b/strong más cercano antes de este grupo
                        if (!questionText) {
                            const allBold = [...document.querySelectorAll('b, strong')];
                            const firstRadioRect = radios[0].getBoundingClientRect();
                            for (let i = allBold.length - 1; i >= 0; i--) {
                                const rect = allBold[i].getBoundingClientRect();
                                if (rect.top < firstRadioRect.top && allBold[i].innerText.trim().length > 5) {
                                    questionText = allBold[i].innerText.trim();
                                    break;
                                }
                            }
                        }

                        const options = radios.map(inp => {
                            const lbl = inp.closest('label');
                            return {
                                value: inp.value,
                                label: lbl ? lbl.innerText.trim() : inp.value,
                                name: inp.name,
                            };
                        });
                        questions.push({ type: 'choice', question: questionText || name, options, name });
                    }

                    // Textareas
                    document.querySelectorAll('textarea').forEach(ta => {
                        const container = ta.closest('div, section, fieldset');
                        const label = container?.querySelector('b, strong, label, h3, h4');
                        let text = label ? label.innerText.trim() : '';
                        if (!text) {
                            // Buscar b/strong antes del textarea
                            const allBold = [...document.querySelectorAll('b, strong')];
                            const taRect = ta.getBoundingClientRect();
                            for (let i = allBold.length - 1; i >= 0; i--) {
                                const rect = allBold[i].getBoundingClientRect();
                                if (rect.top < taRect.top && allBold[i].innerText.trim().length > 5) {
                                    text = allBold[i].innerText.trim();
                                    break;
                                }
                            }
                        }
                        questions.push({
                            type: 'text',
                            question: text || ta.placeholder || ta.name || 'Comentario',
                            maxLength: ta.maxLength > 0 ? ta.maxLength : 500,
                            name: ta.name,
                            selector: ta.id ? '#' + ta.id : null,
                        });
                    });

                    return questions;
                }
            """)

            if not questions_data:
                logger.warning("[Computrabajo] No se detectaron preguntas en la página")
                return False

            logger.info(f"[Computrabajo] {len(questions_data)} preguntas detectadas")

            cv_summary = self._profile_manager.get_cv_summary_for_ai(application.profile)
            questions_text = json.dumps(questions_data, ensure_ascii=False, indent=2)

            response = await self._groq.chat.completions.create(
                model=settings.groq_model_fast,
                max_tokens=1024,
                temperature=0.1,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Sos un asistente que responde preguntas de selección laboral. "
                            "Respondé de forma honesta según el perfil del candidato. "
                            "Para preguntas de opción múltiple, elegí la opción más adecuada. "
                            "Para preguntas de texto, respondé de forma concisa y profesional. "
                            "Devolvé SOLO un JSON con el array 'answers'. Cada answer tiene: "
                            "'question_index' (int), 'selected_value' (para choice) o 'text' (para text)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"PERFIL DEL CANDIDATO:\n{cv_summary}\n\n"
                            f"VACANTE: {application.job.title} en {application.job.company}\n\n"
                            f"PREGUNTAS:\n{questions_text}\n\n"
                            f"Respondé cada pregunta con la mejor opción para este candidato."
                        ),
                    },
                ],
            )

            answers = json.loads(response.choices[0].message.content)
            answer_list = answers.get("answers", [])
            logger.info(f"[Computrabajo] IA generó {len(answer_list)} respuestas")

            for ans in answer_list:
                idx = ans.get("question_index", -1)
                if idx < 0 or idx >= len(questions_data):
                    continue
                q = questions_data[idx]

                if q["type"] == "choice" and "selected_value" in ans:
                    selected = ans["selected_value"]
                    # Buscar la opción que matchea (por label o value)
                    target_opt = None
                    for opt in q.get("options", []):
                        if opt["label"] == selected or opt["value"] == selected:
                            target_opt = opt
                            break
                    if not target_opt:
                        # Fallback: match parcial
                        for opt in q.get("options", []):
                            if selected.lower() in opt["label"].lower():
                                target_opt = opt
                                break
                    if target_opt:
                        # Click vía name+value (más confiable que id)
                        clicked = await page.evaluate(
                            """([name, value]) => {
                                const inp = document.querySelector('input[name="' + name + '"][value="' + value + '"]');
                                if (inp) {
                                    const label = inp.closest('label');
                                    if (label) { label.click(); return true; }
                                    inp.checked = true;
                                    inp.click();
                                    inp.dispatchEvent(new Event('change', {bubbles: true}));
                                    return true;
                                }
                                return false;
                            }""", [target_opt.get("name", ""), target_opt["value"]]
                        )
                        if not clicked:
                            # Fallback: click por texto del label
                            await page.evaluate(
                                """(labelText) => {
                                    const labels = [...document.querySelectorAll('label')];
                                    const lbl = labels.find(l => l.innerText.trim() === labelText);
                                    if (lbl) lbl.click();
                                }""", target_opt["label"]
                            )
                    await self.human_delay(0.5, 1)

                elif q["type"] == "text" and "text" in ans:
                    text_val = ans["text"][:q.get("maxLength", 500)]
                    filled = False
                    if q.get("selector"):
                        filled = await page.evaluate(
                            """([sel, val]) => {
                                const el = document.querySelector(sel);
                                if (el) {
                                    el.style.display = 'block';
                                    el.style.visibility = 'visible';
                                    el.value = val;
                                    el.dispatchEvent(new Event('input', {bubbles: true}));
                                    el.dispatchEvent(new Event('change', {bubbles: true}));
                                    return true;
                                }
                                return false;
                            }""", [q["selector"], text_val]
                        )
                    if not filled:
                        # Fallback: llenar el n-ésimo textarea visible
                        ta_idx = sum(1 for qq in questions_data[:idx] if qq["type"] == "text")
                        filled = await page.evaluate(
                            """([taIdx, val]) => {
                                const tas = [...document.querySelectorAll('textarea')];
                                if (taIdx < tas.length) {
                                    const ta = tas[taIdx];
                                    ta.style.display = 'block';
                                    ta.style.visibility = 'visible';
                                    ta.value = val;
                                    ta.dispatchEvent(new Event('input', {bubbles: true}));
                                    ta.dispatchEvent(new Event('change', {bubbles: true}));
                                    return true;
                                }
                                return false;
                            }""", [ta_idx, text_val]
                        )
                    await self.human_delay(0.5, 1)

            return True

        except Exception as e:
            logger.error(f"[Computrabajo] Error respondiendo preguntas: {e}")
            return False

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

            if application.status != ApplicationStatus.APPLIED:
                await self._screenshot_failure(page, application)
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

            if application.status != ApplicationStatus.APPLIED:
                await self._screenshot_failure(page, application)
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

    # ─── Helpers ─────────────────────────────────────────────────────────────

    async def _screenshot_failure(self, page: Page, application: Application):
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = re.sub(r"[^\w]", "_", application.job.title[:30])
        portal = application.job.portal.value
        path = SCREENSHOTS_DIR / f"{portal}_{safe_title}_{ts}.png"
        try:
            await page.screenshot(path=str(path), full_page=False)
            logger.info(f"Screenshot guardado: {path}")
            application.notes = (application.notes or "") + f" | Screenshot: {path.name}"
        except Exception as e:
            logger.warning(f"No se pudo tomar screenshot: {e}")

    # ─── BaseScraper stubs ────────────────────────────────────────────────────

    async def search(self, config):
        raise NotImplementedError

    async def get_job_detail(self, url: str):
        raise NotImplementedError
