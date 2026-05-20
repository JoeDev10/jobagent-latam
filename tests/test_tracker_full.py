"""
Tests completos del ApplicationTracker (base de datos SQLite).

Cubre:
  - CRUD de vacantes (save, exists, get, filter)
  - CRUD de aplicaciones (save, update_status, get_full, filter por estado)
  - Cálculo de estadísticas (total, avg_score, by_status)
  - Casos límite: DB vacía, IDs inexistentes, actualizar estado a APPLIED
    (que automáticamente guarda applied_at)

Nota: cada test usa una DB en tmp_path — nunca toca la DB real de la app.
"""
import uuid
import pytest

from core import Application, ApplicationStatus, ExperienceLevel, JobModality, Portal, UserProfile


# ─── Fixture: tracker aislado en DB temporal ─────────────────────────────────

@pytest.fixture
def tracker(tmp_path, monkeypatch):
    """Retorna un ApplicationTracker que usa una DB temporal (no la real)."""
    from modules.tracker import database as db_module
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    return db_module.ApplicationTracker()


@pytest.fixture
def app_con_carta(sample_job, sample_profile):
    """Application con carta de presentación lista."""
    return Application(
        id=str(uuid.uuid4()),
        job=sample_job,
        profile=sample_profile,
        status=ApplicationStatus.PENDING,
        cover_letter="Me interesa el puesto de QA Tester en Acme Corp.",
    )


# ─── Tests de vacantes ────────────────────────────────────────────────────────

class TestJobCRUD:

    def test_job_no_existe_antes_de_guardar(self, tracker, sample_job):
        assert tracker.job_exists(sample_job.url) is False

    def test_job_existe_despues_de_guardar(self, tracker, sample_job):
        tracker.save_job(sample_job)
        assert tracker.job_exists(sample_job.url) is True

    def test_save_job_idempotente(self, tracker, sample_job):
        """Guardar el mismo job dos veces no crea duplicados."""
        tracker.save_job(sample_job)
        tracker.save_job(sample_job)
        jobs = tracker.get_jobs(min_score=0.0)
        assert len(jobs) == 1

    def test_get_jobs_filtra_por_score_minimo(self, tracker, sample_job):
        sample_job.relevance_score = 0.85
        tracker.save_job(sample_job)

        resultado_alto = tracker.get_jobs(min_score=0.9)
        resultado_bajo = tracker.get_jobs(min_score=0.8)

        assert len(resultado_alto) == 0   # 0.85 < 0.9 → no aparece
        assert len(resultado_bajo) == 1   # 0.85 >= 0.8 → sí aparece

    def test_get_jobs_filtra_por_portal(self, tracker, sample_job):
        sample_job.relevance_score = 0.80
        tracker.save_job(sample_job)  # portal = COMPUTRABAJO

        en_computrabajo = tracker.get_jobs(min_score=0.0, portal=Portal.COMPUTRABAJO)
        en_bumeran = tracker.get_jobs(min_score=0.0, portal=Portal.BUMERAN)

        assert len(en_computrabajo) == 1
        assert len(en_bumeran) == 0

    def test_get_jobs_respeta_limit(self, tracker, sample_job):
        for i in range(5):
            job = sample_job.model_copy(update={
                "id": str(uuid.uuid4()),
                "url": f"https://example.com/job/{i}",
                "relevance_score": 0.70,
            })
            tracker.save_job(job)

        resultado = tracker.get_jobs(min_score=0.0, limit=3)
        assert len(resultado) == 3

    def test_get_jobs_ordena_por_score_descendente(self, tracker, sample_job):
        scores = [0.60, 0.90, 0.75]
        for i, score in enumerate(scores):
            job = sample_job.model_copy(update={
                "id": str(uuid.uuid4()),
                "url": f"https://example.com/job/{i}",
                "relevance_score": score,
            })
            tracker.save_job(job)

        result = tracker.get_jobs(min_score=0.0)
        scores_result = [j.relevance_score for j in result]
        assert scores_result == sorted(scores_result, reverse=True)


# ─── Tests de aplicaciones ────────────────────────────────────────────────────

class TestApplicationCRUD:

    def test_save_application_basico(self, tracker, app_con_carta):
        tracker.save_job(app_con_carta.job)
        tracker.save_application(app_con_carta)
        apps = tracker.get_applications()
        assert len(apps) == 1
        assert apps[0]["id"] == app_con_carta.id

    def test_estado_inicial_es_pendiente(self, tracker, app_con_carta):
        tracker.save_job(app_con_carta.job)
        tracker.save_application(app_con_carta)
        apps = tracker.get_applications()
        assert apps[0]["status"] == "pendiente"

    def test_save_application_idempotente(self, tracker, app_con_carta):
        """Guardar la misma aplicación dos veces no crea duplicados."""
        tracker.save_job(app_con_carta.job)
        tracker.save_application(app_con_carta)
        tracker.save_application(app_con_carta)
        assert len(tracker.get_applications()) == 1

    def test_update_status_cambia_estado(self, tracker, app_con_carta):
        tracker.save_job(app_con_carta.job)
        tracker.save_application(app_con_carta)

        tracker.update_status(app_con_carta.id, ApplicationStatus.APPLIED)

        apps = tracker.get_applications()
        assert apps[0]["status"] == "aplicada"

    def test_update_status_applied_guarda_applied_at(self, tracker, app_con_carta):
        """Cuando el estado pasa a APPLIED, applied_at debe quedar registrado."""
        tracker.save_job(app_con_carta.job)
        tracker.save_application(app_con_carta)

        tracker.update_status(app_con_carta.id, ApplicationStatus.APPLIED)

        apps = tracker.get_applications()
        assert apps[0]["applied_at"] is not None

    def test_update_status_no_applied_no_cambia_applied_at(self, tracker, app_con_carta):
        """Estados como INTERVIEW no sobreescriben applied_at."""
        tracker.save_job(app_con_carta.job)
        tracker.save_application(app_con_carta)

        tracker.update_status(app_con_carta.id, ApplicationStatus.INTERVIEW)

        apps = tracker.get_applications()
        assert apps[0]["applied_at"] is None

    def test_update_status_con_notes(self, tracker, app_con_carta):
        tracker.save_job(app_con_carta.job)
        tracker.save_application(app_con_carta)

        nota = "Entrevista el martes a las 10am"
        tracker.update_status(app_con_carta.id, ApplicationStatus.INTERVIEW, notes=nota)

        apps = tracker.get_applications()
        assert apps[0]["notes"] == nota

    def test_get_applications_filtra_por_estado(self, tracker, sample_job, sample_profile):
        """Crear apps con distintos estados y verificar que el filtro funciona."""
        for status in [ApplicationStatus.PENDING, ApplicationStatus.APPLIED, ApplicationStatus.DISCARDED]:
            job = sample_job.model_copy(update={
                "id": str(uuid.uuid4()),
                "url": f"https://x.com/{status.value}",
            })
            app = Application(
                id=str(uuid.uuid4()),
                job=job,
                profile=sample_profile,
                status=status,
            )
            tracker.save_job(app.job)
            tracker.save_application(app)

        pendientes = tracker.get_applications(ApplicationStatus.PENDING)
        aplicadas = tracker.get_applications(ApplicationStatus.APPLIED)
        todas = tracker.get_applications()

        assert len(pendientes) == 1
        assert len(aplicadas) == 1
        assert len(todas) == 3

    def test_get_application_full_reconstruye_correctamente(self, tracker, app_con_carta, sample_profile):
        tracker.save_job(app_con_carta.job)
        tracker.save_application(app_con_carta)

        full = tracker.get_application_full(app_con_carta.id, profile=sample_profile)

        assert full is not None
        assert full.id == app_con_carta.id
        assert full.job.title == app_con_carta.job.title
        assert full.cover_letter == app_con_carta.cover_letter
        assert full.status == ApplicationStatus.PENDING

    def test_get_application_full_id_inexistente_devuelve_none(self, tracker):
        result = tracker.get_application_full("id-que-no-existe")
        assert result is None


# ─── Tests de estadísticas ────────────────────────────────────────────────────

class TestStats:

    def test_stats_db_vacia(self, tracker):
        stats = tracker.get_stats()
        assert stats["total_jobs_scraped"] == 0
        assert stats["total_applications"] == 0
        assert stats["avg_relevance_score"] == 0.0
        assert stats["by_status"] == {}

    def test_stats_total_jobs(self, tracker, sample_job):
        tracker.save_job(sample_job)
        assert tracker.get_stats()["total_jobs_scraped"] == 1

    def test_stats_avg_score(self, tracker, sample_job):
        """El promedio se calcula solo sobre vacantes con score asignado."""
        job_con_score = sample_job.model_copy(update={"relevance_score": 0.80})
        tracker.save_job(job_con_score)

        job_sin_score = sample_job.model_copy(update={
            "id": str(uuid.uuid4()),
            "url": "https://example.com/job/sin-score",
            "relevance_score": None,
        })
        tracker.save_job(job_sin_score)

        stats = tracker.get_stats()
        assert stats["avg_relevance_score"] == pytest.approx(0.80)

    def test_stats_by_status(self, tracker, sample_job, sample_profile):
        """by_status cuenta correctamente aplicaciones por estado."""
        for i, status in enumerate([ApplicationStatus.APPLIED, ApplicationStatus.APPLIED, ApplicationStatus.PENDING]):
            job = sample_job.model_copy(update={"id": str(uuid.uuid4()), "url": f"https://x.com/{i}"})
            app = Application(
                id=str(uuid.uuid4()),
                job=job,
                profile=sample_profile,
                status=status,
            )
            tracker.save_job(app.job)
            tracker.save_application(app)

        by_status = tracker.get_stats()["by_status"]
        assert by_status.get("aplicada") == 2
        assert by_status.get("pendiente") == 1

    @pytest.mark.parametrize("n_jobs", [0, 1, 5, 10])
    def test_stats_total_jobs_coincide_con_cantidad_guardada(self, tracker, sample_job, n_jobs):
        for i in range(n_jobs):
            job = sample_job.model_copy(update={"id": str(uuid.uuid4()), "url": f"https://x.com/{i}"})
            tracker.save_job(job)
        assert tracker.get_stats()["total_jobs_scraped"] == n_jobs
