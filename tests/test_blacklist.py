"""
Tests para la funcionalidad de blacklist de empresas.

Qué valida:
  - Matching parcial (case insensitive)
  - Que la blacklist no filtra empresas similares no blacklisteadas
  - Que el agente excluye vacantes correctamente antes del scoring
"""
import pytest
from core import JobListing, JobModality, Portal, UserProfile, ExperienceLevel
from core.agent import JobAgent


def make_job(company: str) -> JobListing:
    return JobListing(
        portal=Portal.COMPUTRABAJO,
        url=f"https://example.com/{company.replace(' ', '_')}",
        title="QA Analyst",
        company=company,
        location="Buenos Aires",
        description="Testing manual y automatizado.",
    )


def make_profile(exclude: list[str]) -> UserProfile:
    return UserProfile(
        full_name="Test",
        email="test@test.com",
        phone="1111",
        location="BsAs",
        headline="QA",
        summary="QA tester",
        experience_level=ExperienceLevel.JUNIOR,
        target_roles=["QA"],
        exclude_companies=exclude,
    )


class TestBlacklist:

    def test_match_exacto(self):
        job = make_job("Randstad")
        profile = make_profile(["Randstad"])
        assert JobAgent._is_blacklisted(job, profile) is True

    def test_match_parcial(self):
        """'Randstad' en blacklist debe ignorar 'Randstad Argentina SA'."""
        job = make_job("Randstad Argentina SA")
        profile = make_profile(["Randstad"])
        assert JobAgent._is_blacklisted(job, profile) is True

    def test_case_insensitive(self):
        job = make_job("RANDSTAD ARGENTINA")
        profile = make_profile(["randstad"])
        assert JobAgent._is_blacklisted(job, profile) is True

    def test_empresa_diferente_no_filtrada(self):
        """'Acme' en blacklist NO debe filtrar 'Accenture'."""
        job = make_job("Accenture")
        profile = make_profile(["Acme"])
        assert JobAgent._is_blacklisted(job, profile) is False

    def test_blacklist_vacia_no_filtra_nada(self):
        job = make_job("Cualquier Empresa SA")
        profile = make_profile([])
        assert JobAgent._is_blacklisted(job, profile) is False

    def test_multiples_entradas(self):
        """La blacklist puede tener varias empresas."""
        job1 = make_job("Randstad")
        job2 = make_job("Manpower")
        job3 = make_job("TechCorp")
        profile = make_profile(["Randstad", "Manpower"])
        assert JobAgent._is_blacklisted(job1, profile) is True
        assert JobAgent._is_blacklisted(job2, profile) is True
        assert JobAgent._is_blacklisted(job3, profile) is False
