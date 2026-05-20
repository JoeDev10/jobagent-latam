from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    app_name: str = "JobAgent LATAM"
    debug: bool = False
    log_level: str = "INFO"

    # IA
    groq_api_key: str = Field(..., env="GROQ_API_KEY")
    groq_model: str = "llama-3.3-70b-versatile"       # cover letters — calidad alta
    groq_model_fast: str = "llama-3.1-8b-instant"     # scoring — 500k tokens/día

    # Base de datos
    database_url: str = "sqlite:///./data/jobagent.db"

    # Playwright
    headless: bool = True
    slow_mo: int = 50

    # Límites
    max_applications_per_day: int = 30
    min_delay_between_actions: int = 2
    max_delay_between_actions: int = 5

    # Credenciales Computrabajo
    computrabajo_email: Optional[str] = Field(None, env="COMPUTRABAJO_EMAIL")
    computrabajo_password: Optional[str] = Field(None, env="COMPUTRABAJO_PASSWORD")

    # Credenciales Bumeran
    bumeran_email: Optional[str] = Field(None, env="BUMERAN_EMAIL")
    bumeran_password: Optional[str] = Field(None, env="BUMERAN_PASSWORD")

    # Credenciales ZonaJobs
    zonajobs_email: Optional[str] = Field(None, env="ZONAJOBS_EMAIL")
    zonajobs_password: Optional[str] = Field(None, env="ZONAJOBS_PASSWORD")

    # Telegram (notificaciones)
    telegram_bot_token: Optional[str] = Field(None, env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(None, env="TELEGRAM_CHAT_ID")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
