"""
Tests de validación de modelos Pydantic y reglas de negocio.

Qué valida:
  - Que los modelos aceptan datos válidos
  - Que los valores por defecto son los esperados
  - Que el serializado/deserializado (roundtrip) conserva los datos
  - Comportamiento de edge cases (campos None, listas vacías)
"""
import pytest
from core import (
    Application, ApplicationStatus, JobListing, JobModality,
    Portal, SearchConfig, UserProfile, ExperienceLevel,
)


class TestJobListing:

    def test_campos_obligatorios(self):
        job = JobListing(
            portal=Portal.COMPUTRABAJO,
            url="https://example.com/job/1",
            title="QA Tester",
            company="Acme",
            location="Buenos Aires",
            description="Descripción del puesto.",
        )
        assert job.relevance_score is None     # no evaluado aún
        assert job.requirements == []          # lista vacía por defecto
        assert job.match_strengths == []
        assert job.match_gaps == []

    def test_score_fuera_de_rango_no_rompe_el_modelo(self):
        """Pydantic no restringe el rango del score — lo valida la lógica de negocio."""
        job = JobListing(
            portal=Portal.BUMERAN,
            url="https://example.com/job/2",
            title="Dev",
            company="Corp",
            location="CABA",
            description="x",
            relevance_score=1.5,  # valor inválido para el negocio pero Pydantic lo acepta
        )
        assert job.relevance_score == 1.5  # documenta el comportamiento actual

    def test_roundtrip_json(self, sample_job):
        json_str = sample_job.model_dump_json()
        restored = JobListing.model_validate_json(json_str)
        assert restored.url == sample_job.url
        assert restored.relevance_score == sample_job.relevance_score
        assert restored.portal == sample_job.portal


class TestUserProfile:

    def test_exclude_companies_default_vacio(self, sample_profile):
        assert sample_profile.exclude_companies == []

    def test_exclude_companies_se_guarda(self):
        profile = UserProfile(
            full_name="Test", email="t@t.com", phone="1",
            location="BsAs", headline="QA", summary="QA tester",
            experience_level=ExperienceLevel.JUNIOR,
            target_roles=["QA"],
            exclude_companies=["Randstad", "Manpower"],
        )
        assert len(profile.exclude_companies) == 2
        assert "Randstad" in profile.exclude_companies

    def test_preferred_modality_default(self, sample_profile):
        assert sample_profile.preferred_modality == JobModality.REMOTE


class TestSearchConfig:

    def test_defaults_seguros(self):
        config = SearchConfig(keywords=["QA"])
        assert config.auto_apply is False            # nunca aplicar sin querer
        assert config.min_relevance_score == 0.65
        assert config.max_results_per_portal == 50
        assert Portal.COMPUTRABAJO in config.portals

    def test_copia_con_update(self):
        """model_copy(update=...) que usa run_auto.py debe funcionar."""
        base = SearchConfig(keywords=["QA"], min_relevance_score=0.65)
        elevated = base.model_copy(update={"min_relevance_score": 0.80})
        assert elevated.min_relevance_score == 0.80
        assert base.min_relevance_score == 0.65        # el original no cambia


class TestApplicationStatus:

    def test_estados_existen(self):
        assert ApplicationStatus.PENDING.value == "pendiente"
        assert ApplicationStatus.APPLIED.value == "aplicada"
        assert ApplicationStatus.INTERVIEW.value == "entrevista"

    def test_estado_desde_string(self):
        status = ApplicationStatus("aplicada")
        assert status == ApplicationStatus.APPLIED
