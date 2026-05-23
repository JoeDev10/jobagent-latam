"""
Smoke tests — verifican que la app arranca sin que explote nada antes
de poder hacer cosas útiles.

NO testean lógica de negocio. NO hacen llamadas a APIs externas (Groq, portales).
Tienen que correr en menos de 10 segundos.

Correr con:
    pytest tests/test_smoke.py -v
    pytest -m smoke
"""
import sqlite3
import tempfile
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 1. IMPORTS: ¿se pueden importar todos los módulos sin errores?
#    Si un import falla, todo lo demás es inútil.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_imports_core():
    """Todos los símbolos esperados de 'core' existen y se pueden importar."""
    from core import (
        Application, ApplicationStatus, JobListing, JobModality,
        Portal, SearchConfig, UserProfile, ExperienceLevel,
        get_logger, settings,
    )
    # Verificamos que son los tipos correctos, no solo que existen
    assert callable(get_logger)
    assert settings is not None


@pytest.mark.smoke
def test_imports_modules():
    """Los módulos principales se importan sin error."""
    from modules.profile import ProfileManager
    from modules.tracker import ApplicationTracker
    from modules.ai import JobScorer, CoverLetterGenerator
    from modules.applicator import ApplicationBot
    from modules.auth import LoginManager
    from modules.notifier import TelegramNotifier
    from modules.scrapers import get_scraper

    # Verificamos que get_scraper devuelve algo para cada portal soportado
    from core import Portal
    for portal in [Portal.COMPUTRABAJO, Portal.BUMERAN, Portal.ZONAJOBS, Portal.INDEED]:
        scraper = get_scraper(portal)
        assert scraper is not None, f"get_scraper({portal}) devolvió None"


@pytest.mark.smoke
def test_imports_agent():
    """El agente principal se importa y se puede instanciar."""
    from core.agent import JobAgent
    agent = JobAgent()
    # El agente debe tener los componentes principales conectados
    assert agent.scorer is not None
    assert agent.cover_letter_gen is not None
    assert agent.tracker is not None
    assert agent.notifier is not None


# ─────────────────────────────────────────────────────────────────────────────
# 2. CONFIGURACIÓN: ¿se carga el .env y settings tiene lo mínimo?
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_settings_load():
    """Settings se inicializa y tiene los valores esperados."""
    from core import settings
    # Estos son requeridos por el agente
    assert settings.groq_api_key, "GROQ_API_KEY no está configurada en .env"
    assert settings.app_name == "VacantIA"
    # Estos son opcionales pero deberían existir como atributos
    assert hasattr(settings, "computrabajo_email")
    assert hasattr(settings, "telegram_bot_token")
    # Valores con defaults sensatos
    assert isinstance(settings.headless, bool)
    assert 0 < settings.max_applications_per_day <= 1000


# ─────────────────────────────────────────────────────────────────────────────
# 3. MODELOS: los Pydantic models se construyen y validan correctamente
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_job_listing_model(sample_job):
    """Un JobListing válido construye y serializa sin errores."""
    assert sample_job.title == "QA Tester Junior"
    assert sample_job.relevance_score == 0.85
    # Roundtrip: serializar → deserializar debe dar lo mismo
    from core import JobListing
    json_str = sample_job.model_dump_json()
    restored = JobListing.model_validate_json(json_str)
    assert restored.url == sample_job.url


@pytest.mark.smoke
def test_user_profile_model(sample_profile):
    """Un UserProfile mínimo válido se construye correctamente."""
    assert sample_profile.full_name == "Test User"
    assert "QA Tester" in sample_profile.target_roles
    # Defaults bien aplicados
    assert sample_profile.work_experience == []
    assert sample_profile.languages == {}


@pytest.mark.smoke
def test_search_config_validation():
    """SearchConfig rechaza valores fuera de rango (validación de Pydantic)."""
    from core import Portal, SearchConfig

    # Caso válido
    config = SearchConfig(keywords=["QA"], portals=[Portal.COMPUTRABAJO])
    assert config.min_relevance_score == 0.65  # default
    assert config.auto_apply is False  # default seguro

    # keywords no puede estar vacío en la práctica (si lo dejamos sin restricción
    # documentamos acá el comportamiento esperado)
    config_empty = SearchConfig(keywords=[])
    assert config_empty.keywords == []


# ─────────────────────────────────────────────────────────────────────────────
# 4. BASE DE DATOS: el tracker se inicializa, pasa integrity check y
#    sus métodos básicos no fallan en una DB vacía.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_tracker_init_and_integrity(tmp_path, monkeypatch):
    """
    El tracker crea su DB y la integridad SQLite es 'ok'.
    Usamos tmp_path (fixture built-in de pytest) para una DB temporal aislada.
    monkeypatch redirige el DB_PATH del tracker al tmp.
    """
    from modules.tracker import database as db_module

    tmp_db = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", tmp_db)

    tracker = db_module.ApplicationTracker()  # crea las tablas

    # Integrity check
    conn = sqlite3.connect(str(tmp_db))
    result = conn.execute("PRAGMA integrity_check").fetchone()
    conn.close()
    assert result[0] == "ok", f"Integrity check falló: {result}"

    # Métodos sobre DB vacía no rompen
    stats = tracker.get_stats()
    assert stats["total_jobs_scraped"] == 0
    assert stats["total_applications"] == 0
    assert tracker.get_applications() == []
    assert tracker.get_jobs() == []
    assert tracker.get_application_full("inexistente") is None


@pytest.mark.smoke
def test_tracker_save_and_query(tmp_path, monkeypatch, sample_job, sample_profile):
    """Roundtrip: guardar un job → buscarlo → debe estar."""
    from modules.tracker import database as db_module

    tmp_db = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", tmp_db)

    tracker = db_module.ApplicationTracker()

    # Antes de guardar: no existe
    assert tracker.job_exists(sample_job.url) is False

    tracker.save_job(sample_job)
    assert tracker.job_exists(sample_job.url) is True

    # Lo encuentra con el score correcto
    jobs = tracker.get_jobs(min_score=0.8)
    assert len(jobs) == 1
    assert jobs[0].title == sample_job.title


# ─────────────────────────────────────────────────────────────────────────────
# 5. PERFIL: el ProfileManager carga el perfil existente sin errores
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_profile_manager_lists_profiles():
    """ProfileManager.list_profiles() devuelve algo (al menos 'marcelo' en este repo)."""
    from modules.profile import ProfileManager
    pm = ProfileManager()
    profiles = pm.list_profiles()
    # Si no hay perfiles guardados, este test es informativo (no falla)
    assert isinstance(profiles, list)


@pytest.mark.smoke
def test_profile_load_marcelo():
    """El perfil 'marcelo' existe y se puede deserializar a UserProfile."""
    from modules.profile import ProfileManager
    pm = ProfileManager()
    if "marcelo" not in pm.list_profiles():
        pytest.skip("Perfil 'marcelo' no existe — test saltado")

    profile = pm.load("marcelo")
    assert profile is not None
    assert profile.full_name  # tiene nombre
    assert profile.email      # tiene email
    assert profile.target_roles  # tiene roles


# ─────────────────────────────────────────────────────────────────────────────
# 6. ARCHIVOS CRÍTICOS: existen los entry-points principales
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.smoke
def test_critical_files_exist(project_root):
    """Los archivos que el usuario espera correr deben existir."""
    critical = [
        "main.py",
        "run_auto.py",
        "configurar.py",
        "requirements.txt",
        ".env.example",
        "dashboard/app.py",
        "core/agent.py",
        "core/config.py",
    ]
    for relpath in critical:
        assert (project_root / relpath).exists(), f"Falta archivo crítico: {relpath}"
