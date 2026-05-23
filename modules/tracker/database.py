"""
ApplicationTracker: persiste vacantes y aplicaciones en SQLite.

Tablas:
  - jobs:         Vacantes encontradas por el scraper
  - applications: Aplicaciones enviadas o pendientes
"""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from core import Application, ApplicationStatus, JobListing, Portal, get_logger

logger = get_logger(__name__)

_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent.parent / "data"))
DB_PATH = _data_dir / "jobagent.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate(conn: sqlite3.Connection):
    """Agrega columnas nuevas si no existen (compatible con SQLite antiguo)."""
    columnas = [
        ("applications", "adapted_cv_path", "TEXT"),
        ("applications", "title",           "TEXT"),
        ("applications", "company",         "TEXT"),
        ("applications", "portal",          "TEXT"),
        ("applications", "url",             "TEXT"),
        ("applications", "location",        "TEXT"),
        ("applications", "salary_range",    "TEXT"),
        ("applications", "relevance_score", "REAL"),
        ("applications", "user_id",         "INTEGER"),
        ("jobs",         "user_id",         "INTEGER"),
    ]
    for table, col, tipo in columnas:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {tipo}")
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_apps_user ON applications(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id)")
    except sqlite3.OperationalError:
        pass
    conn.commit()


def _init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id              TEXT PRIMARY KEY,
            portal          TEXT NOT NULL,
            url             TEXT UNIQUE NOT NULL,
            title           TEXT NOT NULL,
            company         TEXT NOT NULL,
            location        TEXT,
            modality        TEXT,
            salary_range    TEXT,
            description     TEXT,
            requirements    TEXT,   -- JSON array
            posted_at       TEXT,
            scraped_at      TEXT NOT NULL,
            relevance_score REAL,
            relevance_reason TEXT,
            match_strengths  TEXT,   -- JSON array
            match_gaps       TEXT    -- JSON array
        );

        CREATE TABLE IF NOT EXISTS applications (
            id              TEXT PRIMARY KEY,
            job_id          TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pendiente',
            cover_letter    TEXT,
            adapted_cv_path TEXT,
            applied_at      TEXT,
            created_at      TEXT NOT NULL,
            notes           TEXT,
            -- campos denormalizados para queries rapidas
            title           TEXT,
            company         TEXT,
            portal          TEXT,
            url             TEXT,
            location        TEXT,
            salary_range    TEXT,
            relevance_score REAL,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );


        CREATE INDEX IF NOT EXISTS idx_jobs_url         ON jobs(url);
        CREATE INDEX IF NOT EXISTS idx_jobs_portal      ON jobs(portal);
        CREATE INDEX IF NOT EXISTS idx_jobs_score       ON jobs(relevance_score);
        CREATE INDEX IF NOT EXISTS idx_apps_status      ON applications(status);
        CREATE INDEX IF NOT EXISTS idx_apps_created     ON applications(created_at);
    """)
    conn.commit()


class ApplicationTracker:
    """
    Interfaz de alto nivel para persistir y consultar vacantes y aplicaciones.
    Cada método abre/cierra su propia conexión (thread-safe para Streamlit).
    """

    def __init__(self):
        with _connect() as conn:
            _init_db(conn)
            _migrate(conn)

    # ─── Vacantes ─────────────────────────────────────────────────────────────

    def job_exists(self, url: str) -> bool:
        """True si la URL ya fue scrapeada antes."""
        with _connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM jobs WHERE url = ? LIMIT 1", (url,)
            ).fetchone()
            return row is not None

    def save_job(self, job: JobListing) -> None:
        """Inserta o actualiza una vacante. No falla si ya existe."""
        with _connect() as conn:
            conn.execute("""
                INSERT INTO jobs (
                    id, portal, url, title, company, location, modality,
                    salary_range, description, requirements, posted_at, scraped_at,
                    relevance_score, relevance_reason, match_strengths, match_gaps
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(url) DO UPDATE SET
                    relevance_score  = excluded.relevance_score,
                    relevance_reason = excluded.relevance_reason,
                    match_strengths  = excluded.match_strengths,
                    match_gaps       = excluded.match_gaps,
                    title            = excluded.title,
                    company          = excluded.company,
                    description      = excluded.description
            """, (
                job.id,
                job.portal.value,
                job.url,
                job.title,
                job.company,
                job.location,
                job.modality.value if job.modality else None,
                job.salary_range,
                job.description,
                json.dumps(job.requirements, ensure_ascii=False),
                job.posted_at,
                job.scraped_at.isoformat(),
                job.relevance_score,
                job.relevance_reason,
                json.dumps(job.match_strengths, ensure_ascii=False),
                json.dumps(job.match_gaps, ensure_ascii=False),
            ))
            conn.commit()

    def get_jobs(
        self,
        min_score: float = 0.0,
        portal: Optional[Portal] = None,
        limit: int = 100,
    ) -> list[JobListing]:
        """Devuelve vacantes filtradas por score y portal."""
        query = "SELECT * FROM jobs WHERE relevance_score >= ?"
        params: list = [min_score]
        if portal:
            query += " AND portal = ?"
            params.append(portal.value)
        query += " ORDER BY relevance_score DESC, scraped_at DESC LIMIT ?"
        params.append(limit)

        with _connect() as conn:
            rows = conn.execute(query, params).fetchall()

        from core import JobModality
        result = []
        for r in rows:
            try:
                result.append(JobListing(
                    id=r["id"],
                    portal=Portal(r["portal"]),
                    url=r["url"],
                    title=r["title"],
                    company=r["company"],
                    location=r["location"] or "Argentina",
                    modality=JobModality(r["modality"]) if r["modality"] else JobModality.ANY,
                    salary_range=r["salary_range"],
                    description=r["description"] or "",
                    requirements=json.loads(r["requirements"] or "[]"),
                    posted_at=r["posted_at"],
                    scraped_at=datetime.fromisoformat(r["scraped_at"]),
                    relevance_score=r["relevance_score"],
                    relevance_reason=r["relevance_reason"],
                    match_strengths=json.loads(r["match_strengths"] or "[]"),
                    match_gaps=json.loads(r["match_gaps"] or "[]"),
                ))
            except Exception as e:
                logger.warning(f"Error deserializando job {r['id']}: {e}")
        return result

    # ─── Aplicaciones ─────────────────────────────────────────────────────────

    def save_application(self, application: Application) -> None:
        """Inserta una nueva aplicacion. Ignora duplicados (mismo id)."""
        job = application.job
        adapted_cv = getattr(application, "adapted_cv_path", None)
        with _connect() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO applications (
                    id, job_id, status, cover_letter, adapted_cv_path, applied_at,
                    created_at, notes,
                    title, company, portal, url, location, salary_range, relevance_score
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                application.id,
                job.id,
                application.status.value,
                application.cover_letter,
                adapted_cv,
                application.applied_at.isoformat() if application.applied_at else None,
                application.created_at.isoformat(),
                application.notes,
                job.title,
                job.company,
                job.portal.value,
                job.url,
                job.location,
                job.salary_range,
                job.relevance_score,
            ))
            conn.commit()

    def update_status(
        self,
        application_id: str,
        status: ApplicationStatus,
        notes: Optional[str] = None,
    ) -> None:
        """Actualiza el estado de una aplicación."""
        with _connect() as conn:
            applied_at = (
                datetime.now().isoformat()
                if status == ApplicationStatus.APPLIED
                else None
            )
            if applied_at:
                conn.execute(
                    "UPDATE applications SET status=?, notes=?, applied_at=? WHERE id=?",
                    (status.value, notes, applied_at, application_id),
                )
            else:
                conn.execute(
                    "UPDATE applications SET status=?, notes=? WHERE id=?",
                    (status.value, notes, application_id),
                )
            conn.commit()

    def get_application_full(self, application_id: str, profile=None) -> Optional[Application]:
        """
        Reconstruye un Application completo (con JobListing real) desde la DB.
        Se usa desde el dashboard para llamar a ApplicationBot.apply() con un objeto válido.
        Si no se pasa profile, devuelve uno mínimo (el bot de aplicación no lo usa).
        """
        from core import JobModality, UserProfile, ExperienceLevel

        query = """
            SELECT a.*,
                   j.description AS job_description,
                   j.requirements AS job_requirements,
                   j.modality AS job_modality,
                   j.posted_at AS job_posted_at,
                   j.scraped_at AS job_scraped_at,
                   j.relevance_reason AS job_relevance_reason,
                   j.match_strengths AS job_match_strengths,
                   j.match_gaps AS job_match_gaps
            FROM applications a
            LEFT JOIN jobs j ON a.job_id = j.id
            WHERE a.id = ?
        """
        with _connect() as conn:
            row = conn.execute(query, (application_id,)).fetchone()

        if not row:
            return None

        try:
            job = JobListing(
                id=row["job_id"],
                portal=Portal(row["portal"]),
                url=row["url"],
                title=row["title"] or "",
                company=row["company"] or "",
                location=row["location"] or "Argentina",
                modality=JobModality(row["job_modality"]) if row["job_modality"] else JobModality.ANY,
                salary_range=row["salary_range"],
                description=row["job_description"] or "",
                requirements=json.loads(row["job_requirements"] or "[]"),
                posted_at=row["job_posted_at"],
                scraped_at=datetime.fromisoformat(row["job_scraped_at"]) if row["job_scraped_at"] else datetime.now(),
                relevance_score=row["relevance_score"],
                relevance_reason=row["job_relevance_reason"],
                match_strengths=json.loads(row["job_match_strengths"] or "[]"),
                match_gaps=json.loads(row["job_match_gaps"] or "[]"),
            )
        except Exception as e:
            logger.error(f"Error reconstruyendo job de application {application_id}: {e}")
            return None

        if profile is None:
            profile = UserProfile(
                full_name="", email="", phone="", location="",
                headline="", summary="",
                experience_level=ExperienceLevel.JUNIOR,
                target_roles=[],
            )

        return Application(
            id=row["id"],
            job=job,
            profile=profile,
            status=ApplicationStatus(row["status"]),
            cover_letter=row["cover_letter"],
            adapted_cv_path=row["adapted_cv_path"],
            applied_at=datetime.fromisoformat(row["applied_at"]) if row["applied_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
            notes=row["notes"],
        )

    def save_cover_letter(self, app_id: str, letter: str) -> None:
        """Guarda la carta de presentación generada en la aplicación."""
        with _connect() as conn:
            conn.execute(
                "UPDATE applications SET cover_letter = ? WHERE id = ?",
                (letter, app_id),
            )
            conn.commit()

    def stamp_user_id(self, user_id: int, app_ids: list) -> None:
        """Marca con user_id las aplicaciones recién creadas por el bot."""
        if not app_ids:
            return
        with _connect() as conn:
            placeholders = ",".join("?" * len(app_ids))
            conn.execute(
                f"UPDATE applications SET user_id = ? WHERE id IN ({placeholders}) AND user_id IS NULL",
                [user_id] + list(app_ids),
            )
            conn.commit()

    def get_applications(
        self,
        status: Optional[ApplicationStatus] = None,
        user_id: Optional[int] = None,
    ) -> list[dict]:
        """Devuelve aplicaciones con datos del job (JOIN). user_id=None devuelve todas."""
        conditions, params = [], []
        if status:
            conditions.append("a.status = ?")
            params.append(status.value)
        if user_id is not None:
            conditions.append("a.user_id = ?")
            params.append(user_id)
        query = """
            SELECT a.*,
                   j.relevance_reason,
                   j.match_strengths,
                   j.match_gaps,
                   j.modality AS job_modality,
                   j.description AS job_description
            FROM applications a
            LEFT JOIN jobs j ON a.job_id = j.id
        """
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY COALESCE(a.relevance_score, 0) DESC, a.created_at DESC"

        with _connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [dict(r) for r in rows]

    # ─── Estadísticas ─────────────────────────────────────────────────────────

    def get_stats(self, user_id: Optional[int] = None) -> dict:
        """Devuelve estadísticas. Si se pasa user_id, filtra por ese usuario."""
        uid_clause = "AND user_id = ?" if user_id is not None else ""
        uid_params = [user_id] if user_id is not None else []

        with _connect() as conn:
            total_jobs = conn.execute(
                f"SELECT COUNT(*) FROM jobs WHERE 1=1 {uid_clause}", uid_params
            ).fetchone()[0]

            total_apps = conn.execute(
                f"SELECT COUNT(*) FROM applications WHERE 1=1 {uid_clause}", uid_params
            ).fetchone()[0]

            avg_score = conn.execute(
                f"SELECT AVG(relevance_score) FROM applications WHERE relevance_score IS NOT NULL {uid_clause}",
                uid_params,
            ).fetchone()[0] or 0.0

            by_status_rows = conn.execute(
                f"SELECT status, COUNT(*) as cnt FROM applications WHERE 1=1 {uid_clause} GROUP BY status",
                uid_params,
            ).fetchall()

        by_status = {r["status"]: r["cnt"] for r in by_status_rows}

        return {
            "total_jobs_scraped": total_jobs,
            "total_applications": total_apps,
            "avg_relevance_score": round(avg_score, 3),
            "by_status": by_status,
        }
