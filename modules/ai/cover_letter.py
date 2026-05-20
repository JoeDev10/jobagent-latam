"""
Generador de cartas de presentación personalizadas con Groq/Llama.
Cada carta se adapta 100% a la vacante y al perfil del candidato.
"""
import asyncio

from groq import AsyncGroq

from core import Application, JobListing, UserProfile, get_logger, settings
from modules.profile import ProfileManager

logger = get_logger(__name__)

_MAX_CONCURRENT = 2  # cartas en paralelo; las cover letters consumen ~1k tokens c/u


class CoverLetterGenerator:
    def __init__(self):
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.profile_manager = ProfileManager()
        self._cv_cache: dict[str, str] = {}
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

    def _cv_summary(self, profile: UserProfile) -> str:
        key = profile.email
        if key not in self._cv_cache:
            self._cv_cache[key] = self.profile_manager.get_cv_summary_for_ai(profile)
        return self._cv_cache[key]

    async def generate(self, job: JobListing, profile: UserProfile) -> str:
        """
        Genera una carta de presentación personalizada para la vacante.
        La carta menciona detalles específicos del puesto y conecta con el perfil.
        """
        cv_summary = self._cv_summary(profile)

        user_content = f"""PERFIL DEL CANDIDATO:
{cv_summary}

VACANTE:
Título: {job.title}
Empresa: {job.company}
Ubicación: {job.location}
Descripción del puesto:
{job.description[:2500]}

Requisitos:
{chr(10).join(f"- {r}" for r in job.requirements[:12])}

Por qué es un buen match:
{chr(10).join(f"- {s}" for s in job.match_strengths)}

---

Escribí una carta de presentación profesional y personalizada siguiendo estas reglas:

1. TONO: Profesional pero cercano, natural en español rioplatense (vos, no tú)
2. EXTENSIÓN: 3-4 párrafos, máximo 300 palabras
3. ESTRUCTURA:
   - Párrafo 1: Por qué te interesa ESA empresa/puesto específicamente (mencioná algo concreto de la descripción)
   - Párrafo 2: Tu experiencia más relevante para ESTE puesto (con logro concreto y número si es posible)
   - Párrafo 3: Qué podés aportar específicamente a este rol
   - Cierre: Breve, con llamada a la acción
4. NO usar frases cliché como "soy una persona proactiva y dinámica"
5. NO mencionar que es una carta generada por IA
6. Personalizar con detalles reales del puesto y la empresa
7. Escribir en primera persona

Devolvé SOLO el texto de la carta, sin asunto, sin "Estimado/a", sin firmas."""

        async with self._semaphore:
            response = await self.client.chat.completions.create(
                model=settings.groq_model,
                max_tokens=1024,
                temperature=0.7,
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un experto en redacción de cartas de presentación para el mercado laboral latinoamericano. Escribís en español rioplatense.",
                    },
                    {
                        "role": "user",
                        "content": user_content,
                    },
                ],
            )

        letter = response.choices[0].message.content.strip()
        logger.info(f"Carta generada para: {job.title} @ {job.company} ({len(letter)} chars)")
        return letter

    async def generate_for_application(self, application: Application) -> Application:
        """Genera la carta y la adjunta a la aplicación."""
        letter = await self.generate(application.job, application.profile)
        application.cover_letter = letter
        return application

    def format_for_portal(self, letter: str, portal: str) -> str:
        limits = {
            "computrabajo": 3000,
            "bumeran": 2000,
            "indeed": 2500,
            "linkedin": 2000,
        }
        limit = limits.get(portal.lower(), 3000)
        if len(letter) > limit:
            letter = letter[:limit - 3] + "..."
            logger.warning(f"Carta truncada a {limit} chars para {portal}")
        return letter
