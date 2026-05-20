from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ExperienceLevel(str, Enum):
    JUNIOR = "junior"
    SEMI_SENIOR = "semi_senior"
    SENIOR = "senior"
    LEAD = "lead"


class JobModality(str, Enum):
    REMOTE = "remoto"
    HYBRID = "hibrido"
    ONSITE = "presencial"
    ANY = "cualquiera"


class ApplicationStatus(str, Enum):
    PENDING = "pendiente"
    APPROVED = "aprobada"
    APPLIED = "aplicada"
    REJECTED = "rechazada"
    INTERVIEW = "entrevista"
    OFFER = "oferta"
    DISCARDED = "descartada"


class Portal(str, Enum):
    COMPUTRABAJO = "computrabajo"
    INDEED = "indeed"
    BUMERAN = "bumeran"
    LINKEDIN = "linkedin"
    ZONAJOBS = "zonajobs"


# ─── Perfil de usuario ────────────────────────────────────────────────────────

class WorkExperience(BaseModel):
    company: str
    role: str
    start_date: str
    end_date: Optional[str] = "Actual"
    description: str
    achievements: list[str] = []


class Education(BaseModel):
    institution: str
    degree: str
    field: str
    start_year: int
    end_year: Optional[int] = None
    completed: bool = True


class UserProfile(BaseModel):
    # Datos personales
    full_name: str
    email: str
    phone: str
    location: str
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None

    # Perfil profesional
    headline: str = Field(description="Título profesional corto, ej: 'Desarrollador Python Senior'")
    summary: str = Field(description="Resumen profesional de 2-3 párrafos")
    experience_level: ExperienceLevel

    # Experiencia y formación
    work_experience: list[WorkExperience] = []
    education: list[Education] = []

    # Skills
    hard_skills: list[str] = []
    soft_skills: list[str] = []
    languages: dict[str, str] = {}  # {"Español": "Nativo", "Inglés": "B2"}

    # Preferencias de búsqueda
    target_roles: list[str] = Field(description="Roles que querés, ej: ['Analista de datos', 'Data Analyst']")
    target_industries: list[str] = []
    min_salary: Optional[int] = None
    max_commute_km: Optional[int] = None
    preferred_modality: JobModality = JobModality.ANY
    exclude_companies: list[str] = []
    preferred_countries: list[str] = ["Argentina"]
    preferred_portals: list[Portal] = [Portal.COMPUTRABAJO, Portal.BUMERAN]


# ─── Vacante ──────────────────────────────────────────────────────────────────

class JobListing(BaseModel):
    id: Optional[str] = None
    portal: Portal
    url: str
    title: str
    company: str
    location: str
    modality: Optional[JobModality] = None
    salary_range: Optional[str] = None
    description: str
    requirements: list[str] = []
    posted_at: Optional[str] = None
    scraped_at: datetime = Field(default_factory=datetime.now)

    # Evaluación IA
    relevance_score: Optional[float] = None      # 0.0 a 1.0
    relevance_reason: Optional[str] = None
    match_strengths: list[str] = []
    match_gaps: list[str] = []


# ─── Aplicación ───────────────────────────────────────────────────────────────

class Application(BaseModel):
    id: Optional[str] = None
    job: JobListing
    profile: UserProfile
    status: ApplicationStatus = ApplicationStatus.PENDING

    cover_letter: Optional[str] = None
    adapted_cv_path: Optional[str] = None

    applied_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    notes: Optional[str] = None


# ─── Configuración de búsqueda ────────────────────────────────────────────────

class SearchConfig(BaseModel):
    keywords: list[str]
    location: str = "Argentina"
    portals: list[Portal] = [Portal.COMPUTRABAJO]
    modality: JobModality = JobModality.ANY
    max_results_per_portal: int = 50
    min_relevance_score: float = 0.65
    auto_apply: bool = False  # Si False, pide aprobación manual antes de aplicar
