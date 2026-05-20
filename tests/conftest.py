"""
conftest.py — configuración global de pytest.

Las "fixtures" definidas acá están disponibles automáticamente en TODOS los tests.
Son una forma de preparar datos o estado antes de cada test, y limpiarlo después.

Conceptos clave:
  - @pytest.fixture: define una función reusable que provee datos a los tests
  - scope: cuándo se crea/destruye la fixture
      "function" (default) → una por test
      "module" → una por archivo de tests
      "session" → una sola para toda la corrida
"""
import sys
from pathlib import Path

import pytest

# Permite importar core, modules, etc. desde los tests
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Path absoluto a la raíz del proyecto (donde está main.py)."""
    return PROJECT_ROOT


@pytest.fixture
def sample_job():
    """Una JobListing válida de ejemplo, lista para usar en tests."""
    from core import JobListing, JobModality, Portal
    return JobListing(
        id="test-001",
        portal=Portal.COMPUTRABAJO,
        url="https://example.com/job/test-001",
        title="QA Tester Junior",
        company="Acme Corp",
        location="Buenos Aires, Argentina",
        modality=JobModality.REMOTE,
        salary_range="$1.500.000 - $2.000.000",
        description="Buscamos QA tester con experiencia en testing manual.",
        requirements=["Python básico", "Conocimiento de Selenium"],
        relevance_score=0.85,
    )


@pytest.fixture
def sample_profile():
    """Un UserProfile mínimo válido para tests."""
    from core import ExperienceLevel, JobModality, UserProfile
    return UserProfile(
        full_name="Test User",
        email="test@example.com",
        phone="+5491100000000",
        location="Buenos Aires",
        headline="QA Tester Junior",
        summary="Profesional de QA con experiencia en testing manual.",
        experience_level=ExperienceLevel.JUNIOR,
        target_roles=["QA Tester", "QA Analyst"],
        preferred_modality=JobModality.REMOTE,
    )
