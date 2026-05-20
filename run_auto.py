"""
Modo autónomo de JobAgent LATAM.

Diseñado para correr sin intervención humana (scheduled task, cron, etc.).

Comportamiento:
  - Aplica automáticamente SOLO a vacantes con score >= AUTO_APPLY_THRESHOLD (0.80)
  - Guarda el resto como pendientes para revisión manual
  - Notifica cada aplicación y el resumen final por Telegram
  - Evita re-aplicar a vacantes ya procesadas (deduplicación por URL en la DB)

Cómo programarlo en Windows (Task Scheduler):
  Acción: C:\\path\\to\\venv\\Scripts\\python.exe
  Argumentos: C:\\path\\to\\jobagent\\run_auto.py
  Variable de entorno: PYTHONUTF8=1
  Frecuencia: diaria a las 8:00 AM
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console

from core import Portal, JobModality, SearchConfig, get_logger
from core.agent import JobAgent
from modules.profile import ProfileManager
from modules.notifier import TelegramNotifier

logger = get_logger(__name__)
console = Console(legacy_windows=False)

# ─── Argumentos CLI ──────────────────────────────────────────────────────────

def _parse_args() -> str:
    parser = argparse.ArgumentParser(description="JobAgent LATAM — Modo Autónomo")
    parser.add_argument(
        "--perfil", "-p",
        default="marcelo",
        help="Nombre del perfil a usar (default: marcelo). Ejemplo: --perfil juan",
    )
    return parser.parse_args().perfil

SEARCH_CONFIG = SearchConfig(
    keywords=["QA Analyst", "QA Tester", "QA Manual", "QA Automation", "Tester"],
    location="Argentina",
    portals=[Portal.COMPUTRABAJO, Portal.BUMERAN, Portal.ZONAJOBS],
    modality=JobModality.ANY,
    max_results_per_portal=10,
    min_relevance_score=0.60,   # filtro para evaluar
    auto_apply=True,            # aplicar sin confirmación manual
)

# Solo aplica automáticamente a vacantes con este score o más
AUTO_APPLY_THRESHOLD = 0.80


async def main():
    profile_name = _parse_args()
    notifier = TelegramNotifier()
    manager = ProfileManager()

    profile = manager.load(profile_name)
    if not profile:
        msg = f"No se encontró el perfil '{profile_name}'. Corré: python main.py setup"
        console.print(f"[red]{msg}[/red]")
        await notifier.notify_error(msg)
        sys.exit(1)

    console.rule(f"[bold blue]JobAgent LATAM — Modo Autónomo[/bold blue]")
    console.print(f"Perfil: {profile.full_name}")
    console.print(f"Score mínimo para aplicar automáticamente: {AUTO_APPLY_THRESHOLD:.0%}")
    console.print()

    # El agente con auto_apply=True aplica a todo lo que supere min_relevance_score.
    # Nosotros subimos el umbral a AUTO_APPLY_THRESHOLD para ser más selectivos.
    config = SEARCH_CONFIG.model_copy(update={"min_relevance_score": AUTO_APPLY_THRESHOLD})

    agent = JobAgent()
    try:
        await agent.run(profile, config, interactive=False)
    except Exception as e:
        logger.error(f"Error en run autónomo: {e}")
        await notifier.notify_error(f"Error crítico en JobAgent:\n{str(e)[:500]}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
