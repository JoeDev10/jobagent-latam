"""
Tests del motor de scoring IA.

Técnica central: MOCKING — reemplazamos la API de Groq con respuestas
controladas para testear la lógica de negocio sin gastar tokens ni
depender de internet.

Conceptos nuevos vs tests anteriores:
  - @pytest.mark.parametrize: correr el mismo test con múltiples casos de entrada
  - patch.object: reemplazar un método específico de una instancia
  - AsyncMock: equivalente de Mock pero para funciones async (await)
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core import ExperienceLevel, JobListing, JobModality, Portal, UserProfile
from modules.ai.scorer import JobScorer


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def scorer():
    return JobScorer()


@pytest.fixture
def qa_job():
    return JobListing(
        portal=Portal.COMPUTRABAJO,
        url="https://example.com/qa-job",
        title="QA Analyst Junior",
        company="TechCorp SA",
        location="Buenos Aires",
        description="Buscamos QA con experiencia en testing manual y automatizado.",
        requirements=["Testing manual", "Python básico", "Selenium"],
    )


@pytest.fixture
def qa_profile():
    return UserProfile(
        full_name="Marcelo Rodriguez",
        email="marcelo@test.com",
        phone="1111",
        location="Buenos Aires",
        headline="QA Analyst Junior",
        summary="2 años de experiencia en testing manual.",
        experience_level=ExperienceLevel.JUNIOR,
        target_roles=["QA Analyst", "QA Tester"],
        hard_skills=["Testing manual", "Python", "Selenium", "Jira"],
    )


def _mock_groq_response(score: float, reason: str = "Buen match", strengths=None, gaps=None, recommendation="APLICAR"):
    """Helper: construye la respuesta simulada de la API de Groq."""
    payload = {
        "score": score,
        "reason": reason,
        "strengths": strengths or ["Experiencia relevante"],
        "gaps": gaps or [],
        "recommendation": recommendation,
    }
    mock = MagicMock()
    mock.choices[0].message.content = json.dumps(payload)
    return mock


# ─── Tests del parsing de respuesta ──────────────────────────────────────────

class TestScorerParsing:

    @pytest.mark.asyncio
    async def test_score_se_asigna_al_job(self, scorer, qa_job, qa_profile):
        """El score devuelto por la IA se guarda en job.relevance_score."""
        mock_resp = _mock_groq_response(score=0.87)
        with patch.object(scorer.client.chat.completions, "create", new=AsyncMock(return_value=mock_resp)):
            result = await scorer.score(qa_job, qa_profile)
        assert result.relevance_score == pytest.approx(0.87)

    @pytest.mark.asyncio
    async def test_reason_se_asigna(self, scorer, qa_job, qa_profile):
        mock_resp = _mock_groq_response(score=0.75, reason="Buen match para el puesto junior.")
        with patch.object(scorer.client.chat.completions, "create", new=AsyncMock(return_value=mock_resp)):
            result = await scorer.score(qa_job, qa_profile)
        assert "junior" in result.relevance_reason.lower()

    @pytest.mark.asyncio
    async def test_strengths_y_gaps_se_asignan(self, scorer, qa_job, qa_profile):
        mock_resp = _mock_groq_response(
            score=0.80,
            strengths=["Testing manual", "Python"],
            gaps=["Sin experiencia en CI/CD"],
        )
        with patch.object(scorer.client.chat.completions, "create", new=AsyncMock(return_value=mock_resp)):
            result = await scorer.score(qa_job, qa_profile)
        assert "Testing manual" in result.match_strengths
        assert "Sin experiencia en CI/CD" in result.match_gaps

    @pytest.mark.asyncio
    async def test_campo_faltante_no_rompe(self, scorer, qa_job, qa_profile):
        """Si la IA devuelve JSON sin 'reason', no debe explotar — usa string vacío."""
        payload = {"score": 0.70}  # faltan reason, strengths, gaps
        mock = MagicMock()
        mock.choices[0].message.content = json.dumps(payload)
        with patch.object(scorer.client.chat.completions, "create", new=AsyncMock(return_value=mock)):
            result = await scorer.score(qa_job, qa_profile)
        assert result.relevance_score == pytest.approx(0.70)
        assert result.relevance_reason == ""
        assert result.match_strengths == []
        assert result.match_gaps == []


# ─── Tests parametrizados: rangos de score ───────────────────────────────────
#
# @pytest.mark.parametrize corre el mismo test con cada fila de datos.
# Es mucho más limpio que escribir 4 funciones separadas idénticas.

class TestScorerRanges:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("raw_score,expected", [
        (0.95, 0.95),   # score perfecto
        (0.80, 0.80),   # umbral de auto-apply
        (0.65, 0.65),   # umbral mínimo por defecto
        (0.30, 0.30),   # score bajo
        (0.0,  0.0),    # score mínimo absoluto
    ])
    async def test_score_se_parsea_correctamente(self, scorer, qa_job, qa_profile, raw_score, expected):
        mock_resp = _mock_groq_response(score=raw_score)
        with patch.object(scorer.client.chat.completions, "create", new=AsyncMock(return_value=mock_resp)):
            result = await scorer.score(qa_job, qa_profile)
        assert result.relevance_score == pytest.approx(expected)


# ─── Tests del filtrado por score mínimo ─────────────────────────────────────

class TestScorerBatch:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scores,min_score,expected_count", [
        ([0.9, 0.8, 0.7],  0.75, 2),  # solo los dos primeros superan el umbral
        ([0.5, 0.4, 0.3],  0.65, 0),  # ninguno supera
        ([0.9, 0.9, 0.9],  0.65, 3),  # todos superan
        ([0.65],           0.65, 1),  # exactamente en el umbral (incluido)
    ])
    async def test_score_batch_filtra_por_minimo(self, scorer, qa_profile, scores, min_score, expected_count):
        jobs = []
        for i, s in enumerate(scores):
            job = JobListing(
                portal=Portal.COMPUTRABAJO,
                url=f"https://example.com/job/{i}",
                title=f"QA Job {i}",
                company="Corp",
                location="BsAs",
                description="Testing job",
            )
            mock_resp = _mock_groq_response(score=s)
            jobs.append((job, mock_resp))

        async def fake_create(**kwargs):
            # Identifica qué job se está evaluando por el título en el prompt
            content = kwargs["messages"][1]["content"]
            for job, resp in jobs:
                if job.title in content:
                    return resp
            return _mock_groq_response(score=0.0)

        with patch.object(scorer.client.chat.completions, "create", new=AsyncMock(side_effect=fake_create)):
            result = await scorer.score_batch([j for j, _ in jobs], qa_profile, min_score=min_score)

        assert len(result) == expected_count

    @pytest.mark.asyncio
    async def test_score_batch_ordena_por_score_descendente(self, scorer, qa_profile):
        """El batch devuelve las vacantes ordenadas de mayor a menor score."""
        scores = [0.6, 0.9, 0.7]
        jobs = [
            JobListing(portal=Portal.COMPUTRABAJO, url=f"https://x.com/{i}",
                       title=f"Job {i}", company="C", location="BsAs", description="x")
            for i in range(3)
        ]
        responses = [_mock_groq_response(s) for s in scores]

        call_count = 0
        async def fake_create(**kwargs):
            nonlocal call_count
            resp = responses[call_count % len(responses)]
            call_count += 1
            return resp

        with patch.object(scorer.client.chat.completions, "create", new=AsyncMock(side_effect=fake_create)):
            result = await scorer.score_batch(jobs, qa_profile, min_score=0.0)

        result_scores = [j.relevance_score for j in result]
        assert result_scores == sorted(result_scores, reverse=True)
