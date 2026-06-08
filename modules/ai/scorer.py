"""
Motor de scoring: evalúa qué tan relevante es una vacante para el perfil del usuario.
"""
import asyncio
import json

from groq import AsyncGroq

from core import JobListing, UserProfile, get_logger, settings
from modules.profile import ProfileManager

logger = get_logger(__name__)

_MAX_CONCURRENT_SCORES = 3


class JobScorer:
    def __init__(self, api_key: str | None = None):
        self.client = AsyncGroq(api_key=api_key or settings.groq_api_key)
        self.profile_manager = ProfileManager()
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SCORES)
        self._cv_cache: dict[str, str] = {}

    def _cv_summary(self, profile: UserProfile) -> str:
        key = profile.email
        if key not in self._cv_cache:
            self._cv_cache[key] = self.profile_manager.get_cv_summary_for_ai(profile)
        return self._cv_cache[key]

    async def score(self, job: JobListing, profile: UserProfile) -> JobListing:
        """
        Evalúa la relevancia de una vacante para el perfil.
        Retorna el JobListing con relevance_score, reason, strengths y gaps completados.
        """
        cv_summary = self._cv_summary(profile)

        user_content = f"""PERFIL DEL CANDIDATO:
{cv_summary}

VACANTE A EVALUAR:
Título: {job.title}
Empresa: {job.company}
Ubicación: {job.location}
Modalidad: {job.modality.value if job.modality else "No especificada"}
Salario: {job.salary_range or "No especificado"}

Descripción:
{job.description[:3000]}

Requisitos:
{chr(10).join(f"- {r}" for r in job.requirements[:15])}

---

Evaluá qué tan bien este candidato encaja con esta vacante y devolvé un JSON con este formato exacto:
{{
  "score": 0.85,
  "reason": "Explicación breve de por qué es un buen o mal match (2-3 oraciones)",
  "strengths": ["Fortaleza 1", "Fortaleza 2", "Fortaleza 3"],
  "gaps": ["Gap 1", "Gap 2"],
  "recommendation": "APLICAR"
}}

Criterios para el score (0.0 a 1.0):
- 0.8 - 1.0: Excelente match, el candidato cumple casi todos los requisitos
- 0.65 - 0.79: Buen match, cumple los principales requisitos
- 0.5 - 0.64: Match parcial, falta algo importante
- 0.0 - 0.49: No es una buena oportunidad para este candidato

Sé honesto y preciso. Considerá experiencia, skills, modalidad y ubicación.
Devolvé SOLO el JSON, sin markdown ni texto adicional."""

        async with self._semaphore:
            response = await self.client.chat.completions.create(
                model=settings.groq_model_fast,
                max_tokens=512,
                temperature=0.1,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un experto en recursos humanos y selección de personal en LATAM. Respondés siempre en JSON válido.",
                    },
                    {
                        "role": "user",
                        "content": user_content,
                    },
                ],
            )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        job.relevance_score = float(result.get("score", 0.0))
        job.relevance_reason = result.get("reason", "")
        job.match_strengths = result.get("strengths", [])
        job.match_gaps = result.get("gaps", [])

        logger.info(
            f"Score [{job.relevance_score:.2f}] {job.title} @ {job.company} "
            f"-> {result.get('recommendation', '?')}"
        )
        return job

    async def score_batch(
        self, jobs: list[JobListing], profile: UserProfile, min_score: float = 0.65
    ) -> list[JobListing]:
        """Evalúa todas las vacantes en paralelo y filtra por score mínimo."""
        results = await asyncio.gather(
            *[self.score(job, profile) for job in jobs],
            return_exceptions=True,
        )
        scored = []
        for job, result in zip(jobs, results):
            if isinstance(result, Exception):
                logger.warning(f"Error evaluando {job.title}: {result}")
                continue
            if result.relevance_score >= min_score:
                scored.append(result)

        scored.sort(key=lambda j: j.relevance_score or 0, reverse=True)
        logger.info(f"Vacantes relevantes: {len(scored)}/{len(jobs)} (score >= {min_score})")
        return scored
