"""
Helpers para ejecutar tareas async (búsqueda, aplicación) desde Streamlit.

Streamlit corre sincronamente cada interacción de usuario, así que envolvemos
las corrutinas con asyncio.run() y guardamos los mensajes de progreso en un
buffer para mostrarlos al terminar.
"""
import asyncio
from typing import Callable, Optional

from core import Application, SearchConfig, UserProfile
from core.agent import JobAgent
from modules.applicator import ApplicationBot
from modules.tracker import ApplicationTracker


def _run(coro):
    """Ejecuta una corrutina creando un event loop nuevo (compatible con Streamlit)."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        except Exception:
            pass


def run_search(
    profile: UserProfile,
    config: SearchConfig,
    on_progress: Optional[Callable[[str], None]] = None,
) -> list[Application]:
    """
    Corre una búsqueda completa: scraping + scoring + cartas.
    En el dashboard nunca aplicamos automáticamente desde acá — `auto_apply=False`
    y `interactive=False` → todo queda como 'pendiente' para revisar después.
    """
    agent = JobAgent()
    safe_config = config.model_copy(update={"auto_apply": False})

    progress_log: list[str] = []

    def _collect(msg: str):
        progress_log.append(msg)
        if on_progress:
            try:
                on_progress(msg)
            except Exception:
                pass

    applications = _run(
        agent.run(
            profile,
            safe_config,
            interactive=False,
            progress_callback=_collect,
        )
    )
    return applications, progress_log


def apply_one(application_id: str, profile: Optional[UserProfile] = None) -> Application:
    """
    Aplica a UNA sola vacante desde el dashboard.
    Reconstruye el Application desde la DB, dispara el ApplicationBot,
    persiste el resultado y devuelve el Application actualizado.
    """
    tracker = ApplicationTracker()
    app = tracker.get_application_full(application_id, profile=profile)
    if not app:
        raise ValueError(f"No se encontró la aplicación {application_id}")

    async def _go():
        async with ApplicationBot() as bot:
            return await bot.apply(app)

    result = _run(_go())
    tracker.update_status(result.id, result.status, result.notes)
    return result
