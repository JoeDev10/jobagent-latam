"""
Notificador de Telegram.

Setup:
  1. Creá un bot con @BotFather → /newbot → copiá el token
  2. Mandá cualquier mensaje a tu bot
  3. Abrí https://api.telegram.org/bot<TOKEN>/getUpdates → copiá tu chat_id
  4. Agregá TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID al .env
"""
import asyncio
from typing import Optional

import httpx

from core import Application, JobListing, get_logger, settings

logger = get_logger(__name__)


class TelegramNotifier:

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.enabled = bool(self.token and self.chat_id)
        if not self.enabled:
            logger.warning("Telegram desactivado (falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env)")

    async def send(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.enabled:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                })
                if resp.status_code != 200:
                    logger.warning(f"Telegram error {resp.status_code}: {resp.text[:200]}")
                    return False
            return True
        except Exception as e:
            logger.warning(f"Telegram send error: {e}")
            return False

    # ─── Mensajes predefinidos ────────────────────────────────────────────────

    async def notify_search_started(self, portals: list[str], keywords: list[str]):
        text = (
            f"<b>JobAgent inicio busqueda</b>\n\n"
            f"Portales: {', '.join(portals)}\n"
            f"Keywords: {', '.join(keywords)}"
        )
        await self.send(text)

    async def notify_vacantes_found(self, total: int, relevant: int, min_score: float):
        emoji = "fire" if relevant >= 5 else "mag"
        text = (
            f"<b>Busqueda completa</b>\n\n"
            f"Vacantes scrapeadas: {total}\n"
            f"Relevantes (score >= {min_score:.0%}): <b>{relevant}</b>"
        )
        await self.send(text)

    async def notify_top_jobs(self, jobs: list[JobListing], max_show: int = 5):
        if not jobs:
            return
        top = jobs[:max_show]
        lines = [f"<b>Top vacantes encontradas:</b>\n"]
        for i, job in enumerate(top, 1):
            score_bar = self._score_bar(job.relevance_score or 0)
            lines.append(
                f"{i}. <b>{job.title}</b>\n"
                f"   {job.company} | {job.location}\n"
                f"   Score: {score_bar} {(job.relevance_score or 0):.0%}\n"
                f"   <a href='{job.url}'>Ver vacante</a>\n"
            )
        await self.send("\n".join(lines))

    async def notify_applied(self, application: Application):
        job = application.job
        text = (
            f"<b>Aplicacion enviada</b>\n\n"
            f"<b>{job.title}</b>\n"
            f"{job.company} | {job.location}\n"
            f"Score: {(job.relevance_score or 0):.0%}\n"
            f"Portal: {job.portal.value}\n"
            f"<a href='{job.url}'>Ver vacante</a>"
        )
        await self.send(text)

    async def notify_apply_failed(self, application: Application, reason: str):
        job = application.job
        text = (
            f"<b>Aplicacion fallida</b> (requiere manual)\n\n"
            f"{job.title} @ {job.company}\n"
            f"Motivo: {reason}\n"
            f"<a href='{job.url}'>Aplicar manualmente</a>"
        )
        await self.send(text)

    async def notify_daily_summary(self, stats: dict):
        by_status = stats.get("by_status", {})
        text = (
            f"<b>Resumen diario JobAgent</b>\n\n"
            f"Vacantes analizadas: {stats.get('total_jobs_scraped', 0)}\n"
            f"Aplicaciones totales: {stats.get('total_applications', 0)}\n"
            f"Score promedio: {stats.get('avg_relevance_score', 0):.0%}\n\n"
            f"Estado de aplicaciones:\n"
        )
        status_labels = {
            "aplicada": "Enviadas",
            "entrevista": "Entrevistas",
            "oferta": "Ofertas",
            "pendiente": "Pendientes",
            "descartada": "Descartadas",
            "rechazada": "Rechazadas",
        }
        for key, label in status_labels.items():
            count = by_status.get(key, 0)
            if count:
                text += f"  {label}: {count}\n"
        await self.send(text)

    async def notify_error(self, message: str):
        text = f"<b>Error en JobAgent</b>\n\n{message}"
        await self.send(text)

    # ─── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _score_bar(score: float) -> str:
        filled = round(score * 5)
        return "█" * filled + "░" * (5 - filled)
