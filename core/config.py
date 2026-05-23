from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "VacantIA"
    debug: bool = False
    log_level: str = "INFO"

    # IA
    groq_api_key: str = Field(..., alias="GROQ_API_KEY")
    groq_model: str = "llama-3.3-70b-versatile"
    groq_model_fast: str = "llama-3.1-8b-instant"

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
    computrabajo_email: Optional[str] = Field(None, alias="COMPUTRABAJO_EMAIL")
    computrabajo_password: Optional[str] = Field(None, alias="COMPUTRABAJO_PASSWORD")

    # Credenciales Bumeran
    bumeran_email: Optional[str] = Field(None, alias="BUMERAN_EMAIL")
    bumeran_password: Optional[str] = Field(None, alias="BUMERAN_PASSWORD")

    # Credenciales ZonaJobs
    zonajobs_email: Optional[str] = Field(None, alias="ZONAJOBS_EMAIL")
    zonajobs_password: Optional[str] = Field(None, alias="ZONAJOBS_PASSWORD")

    # Telegram
    telegram_bot_token: Optional[str] = Field(None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(None, alias="TELEGRAM_CHAT_ID")


settings = Settings()
