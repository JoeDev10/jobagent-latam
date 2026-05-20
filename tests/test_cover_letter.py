"""
Tests del generador de cartas de presentación.

Estrategia: mockear la API de Groq para no gastar tokens ni depender de internet.
Esto es una técnica clave de QA — aislar el componente bajo test.

Correr con:
    pytest tests/test_cover_letter.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core import Application, ApplicationStatus, ExperienceLevel, JobModality, UserProfile, JobListing, Portal
from modules.ai.cover_letter import CoverLetterGenerator


CARTA_MOCK = """Me interesa el puesto de QA Tester en Acme porque buscan experiencia en testing manual,
que es exactamente mi especialidad. En mi último rol automaticé 50 casos de prueba.
Puedo aportar metodología y criterio para mejorar la calidad del producto.
Quedo a disposición para una entrevista."""


@pytest.fixture
def generator():
    return CoverLetterGenerator()


@pytest.fixture
def sample_app(sample_job, sample_profile):
    return Application(
        id="app-test-001",
        job=sample_job,
        profile=sample_profile,
        status=ApplicationStatus.PENDING,
    )


class TestCoverLetterGenerator:

    @pytest.mark.asyncio
    async def test_genera_carta_no_vacia(self, generator, sample_app):
        """La carta generada no puede estar vacía."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = CARTA_MOCK

        with patch.object(generator.client.chat.completions, "create", new=AsyncMock(return_value=mock_response)):
            letter = await generator.generate(sample_app.job, sample_app.profile)

        assert letter
        assert len(letter) > 50

    @pytest.mark.asyncio
    async def test_carta_se_adjunta_a_aplicacion(self, generator, sample_app):
        """generate_for_application() debe setear application.cover_letter."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = CARTA_MOCK

        with patch.object(generator.client.chat.completions, "create", new=AsyncMock(return_value=mock_response)):
            result = await generator.generate_for_application(sample_app)

        assert result.cover_letter is not None
        assert len(result.cover_letter) > 0

    def test_format_for_portal_trunca_si_es_largo(self, generator):
        """Una carta muy larga debe ser truncada al límite del portal."""
        letra_larga = "A" * 5000
        truncada = generator.format_for_portal(letra_larga, "bumeran")
        assert len(truncada) <= 2003  # 2000 + "..."

    def test_format_for_portal_no_trunca_si_cabe(self, generator):
        carta_corta = "Hola, me interesa el puesto."
        resultado = generator.format_for_portal(carta_corta, "computrabajo")
        assert resultado == carta_corta  # sin cambios

    def test_format_for_portal_desconocido_usa_default(self, generator):
        """Portal desconocido usa el límite por defecto (3000)."""
        carta = "X" * 2500
        resultado = generator.format_for_portal(carta, "portal_inventado")
        assert resultado == carta  # cabe dentro de 3000
