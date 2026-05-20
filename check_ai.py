"""
Test scorer + cover letter con una vacante real de Computrabajo.
"""
import asyncio
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from core import JobListing, Portal, JobModality, UserProfile, ExperienceLevel, WorkExperience
from modules.ai.scorer import JobScorer
from modules.ai.cover_letter import CoverLetterGenerator

# Perfil de prueba mínimo
profile = UserProfile(
    full_name="Juan Pérez",
    email="juan@example.com",
    phone="+54 11 1234-5678",
    location="Buenos Aires, Argentina",
    headline="Desarrollador Python Semi-Senior",
    summary="Desarrollador Python con 3 años de experiencia en backend y APIs REST.",
    experience_level=ExperienceLevel.SEMI_SENIOR,
    work_experience=[
        WorkExperience(
            company="TechCo SA",
            role="Desarrollador Python",
            start_date="2022-01",
            end_date="Actual",
            description="Desarrollo de APIs REST con FastAPI y Django. Integración con bases de datos PostgreSQL.",
            achievements=["Reduje el tiempo de respuesta de la API en 40%"],
        )
    ],
    hard_skills=["Python", "FastAPI", "Django", "PostgreSQL", "Docker", "Git"],
    soft_skills=["Trabajo en equipo", "Comunicación"],
    languages={"Español": "Nativo", "Inglés": "B2"},
    target_roles=["Desarrollador Python", "Backend Developer", "Python Developer"],
    preferred_modality=JobModality.REMOTE,
)

# Vacante de prueba
job = JobListing(
    portal=Portal.COMPUTRABAJO,
    url="https://ar.computrabajo.com/test",
    title="Desarrollador Python Semi-Senior - Remoto",
    company="StartupTech Argentina",
    location="Buenos Aires, Argentina",
    modality=JobModality.REMOTE,
    description=(
        "Buscamos Desarrollador Python SSR para unirse a nuestro equipo de backend. "
        "Trabajarás en el desarrollo de APIs REST con FastAPI, integración con PostgreSQL, "
        "y despliegue en contenedores Docker. Modalidad 100% remota, equipo distribuido. "
        "Ofrecemos contrato en blanco, obra social, bono anual."
    ),
    requirements=[
        "3+ años de experiencia con Python",
        "Experiencia con FastAPI o Django",
        "Conocimiento de PostgreSQL",
        "Familiaridad con Docker",
        "Inglés intermedio",
    ],
)


async def main():
    print("=" * 60)
    print("TEST SCORER")
    print("=" * 60)
    scorer = JobScorer()
    scored_job = await scorer.score(job, profile)
    print(f"Score:      {scored_job.relevance_score:.0%}")
    print(f"Motivo:     {scored_job.relevance_reason}")
    print(f"Fortalezas: {scored_job.match_strengths}")
    print(f"Brechas:    {scored_job.match_gaps}")

    print()
    print("=" * 60)
    print("TEST COVER LETTER")
    print("=" * 60)
    gen = CoverLetterGenerator()
    carta = await gen.generate(scored_job, profile)
    print(carta)
    print(f"\n[{len(carta)} caracteres]")


asyncio.run(main())
