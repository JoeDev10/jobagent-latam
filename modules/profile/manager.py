"""
Gestión del perfil de usuario: crear, cargar, guardar y extraer desde CV.
"""
import json
import os
from pathlib import Path
from typing import Optional

from groq import Groq

from core import UserProfile, get_logger, settings

logger = get_logger(__name__)
PROFILES_DIR = Path("data/profiles")


class ProfileManager:
    def __init__(self):
        self.client = Groq(api_key=settings.groq_api_key)
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    # ─── Guardar / Cargar ─────────────────────────────────────────────────────

    def save(self, profile: UserProfile, name: str = "default") -> Path:
        path = PROFILES_DIR / f"{name}.json"
        path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        logger.info(f"Perfil guardado en {path}")
        return path

    def load(self, name: str = "default") -> Optional[UserProfile]:
        path = PROFILES_DIR / f"{name}.json"
        if not path.exists():
            logger.warning(f"No se encontró el perfil '{name}'")
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return UserProfile(**data)

    def list_profiles(self) -> list[str]:
        return [p.stem for p in PROFILES_DIR.glob("*.json")]

    # ─── Extracción desde CV (PDF o texto) ────────────────────────────────────

    def extract_from_cv_text(self, cv_text: str) -> UserProfile:
        """Usa Claude para extraer datos estructurados desde el texto de un CV."""
        logger.info("Extrayendo perfil desde CV con Claude...")

        schema = UserProfile.model_json_schema()

        response = self.client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=4096,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un extractor experto de información de currículums vitae. "
                        "Tu tarea es analizar el CV proporcionado y extraer TODA la información relevante "
                        "en formato JSON estructurado. Sé preciso y completo. Si algo no está en el CV, "
                        "usa valores vacíos/nulos. Respondé ÚNICAMENTE con el JSON, sin texto adicional."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Extrae la información de este CV en formato JSON según este schema:\n\n"
                        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
                        f"CV A ANALIZAR:\n{cv_text}\n\n"
                        f"Devuelve SOLO el JSON válido, sin markdown, sin explicaciones."
                    ),
                },
            ],
        )

        data = json.loads(response.choices[0].message.content)
        profile = UserProfile(**data)
        logger.info(f"Perfil extraído para: {profile.full_name}")
        return profile

    def extract_from_pdf(self, pdf_path: str) -> UserProfile:
        """Extrae texto de un PDF y luego extrae el perfil."""
        try:
            import PyPDF2
            text = ""
            with open(pdf_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            return self.extract_from_cv_text(text)
        except ImportError:
            raise RuntimeError("Instalá PyPDF2: pip install PyPDF2")

    # ─── Completar perfil interactivamente ────────────────────────────────────

    def complete_profile_with_ai(self, partial_profile: UserProfile) -> UserProfile:
        """
        Dado un perfil parcial (ej: extraído de CV), usa Claude para
        inferir/completar campos faltantes como target_roles, summary, etc.
        """
        logger.info("Completando perfil con IA...")

        profile_json = partial_profile.model_dump_json(indent=2)

        response = self.client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=2048,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un consultor de recursos humanos experto en LATAM. "
                        "Dado un perfil profesional incompleto, tu tarea es: "
                        "1. Inferir roles target apropiados según la experiencia. "
                        "2. Mejorar el resumen profesional si está vacío o es débil. "
                        "3. Sugerir industrias target relevantes. "
                        "Respondé ÚNICAMENTE con el JSON del perfil completo y mejorado."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Completá y mejorá este perfil profesional:\n\n{profile_json}\n\nDevuelve el perfil completo como JSON válido.",
                },
            ],
        )

        data = json.loads(response.choices[0].message.content)
        return UserProfile(**data)

    def get_cv_summary_for_ai(self, profile: UserProfile) -> str:
        """Genera un resumen compacto del perfil para usar en prompts de IA."""
        exp_lines = []
        for e in profile.work_experience:
            exp_lines.append(
                f"- {e.role} en {e.company} ({e.start_date} - {e.end_date}): {e.description}"
            )

        edu_lines = []
        for ed in profile.education:
            edu_lines.append(f"- {ed.degree} en {ed.field} ({ed.institution})")

        skills = ", ".join(profile.hard_skills[:15])
        langs = ", ".join([f"{k} ({v})" for k, v in profile.languages.items()])

        return f"""
CANDIDATO: {profile.full_name}
TÍTULO: {profile.headline}
UBICACIÓN: {profile.location}
NIVEL: {profile.experience_level.value}

RESUMEN:
{profile.summary}

EXPERIENCIA:
{chr(10).join(exp_lines)}

EDUCACIÓN:
{chr(10).join(edu_lines)}

HABILIDADES TÉCNICAS: {skills}
IDIOMAS: {langs}

ROLES QUE BUSCA: {", ".join(profile.target_roles)}
MODALIDAD PREFERIDA: {profile.preferred_modality.value}
""".strip()
