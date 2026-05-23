"""
JobAgent LATAM — Punto de entrada principal.

Uso:
  python main.py setup          → Configurar perfil desde CV
  python main.py search         → Buscar y aplicar a vacantes
  python main.py dashboard      → Abrir dashboard web
  python main.py stats          → Ver estadísticas
"""
import asyncio
import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Confirm, Prompt

load_dotenv()

from core import JobModality, Portal, SearchConfig, get_logger
from core.agent import JobAgent
from modules.profile import ProfileManager

logger = get_logger(__name__)
console = Console(legacy_windows=False)


def cmd_setup():
    """Asistente para crear el perfil de usuario."""
    console.rule("[bold blue]Configuración de Perfil[/bold blue]")
    manager = ProfileManager()

    console.print("¿Cómo querés cargar tu perfil?")
    console.print("  1. Desde un CV en PDF")
    console.print("  2. Desde texto (pegás el contenido del CV)")
    console.print("  3. Cargar perfil existente")

    choice = Prompt.ask("Opción", choices=["1", "2", "3"], default="1")

    if choice == "1":
        pdf_path = Prompt.ask("Ruta al PDF de tu CV")
        if not Path(pdf_path).exists():
            console.print(f"[red]No se encontró el archivo: {pdf_path}[/red]")
            return
        console.print("[blue]Extrayendo perfil del CV...[/blue]")
        profile = manager.extract_from_pdf(pdf_path)

    elif choice == "2":
        console.print("Pegá el contenido de tu CV (terminá con una línea que solo diga 'FIN'):")
        lines = []
        while True:
            line = input()
            if line.strip() == "FIN":
                break
            lines.append(line)
        cv_text = "\n".join(lines)
        console.print("[blue]Procesando CV con IA...[/blue]")
        profile = manager.extract_from_cv_text(cv_text)

    else:
        profiles = manager.list_profiles()
        if not profiles:
            console.print("[red]No hay perfiles guardados.[/red]")
            return
        name = Prompt.ask("Nombre del perfil", choices=profiles, default=profiles[0])
        profile = manager.load(name)
        console.print(f"[green]Perfil cargado: {profile.full_name}[/green]")
        return

    # Completar con IA
    if Confirm.ask("¿Querés que la IA mejore y complete tu perfil?", default=True):
        profile = manager.complete_profile_with_ai(profile)

    # Guardar
    profile_name = Prompt.ask("Nombre para este perfil", default="default")
    path = manager.save(profile, profile_name)
    console.print(f"\n[green]✓ Perfil guardado: {path}[/green]")
    console.print(f"  Nombre: {profile.full_name}")
    console.print(f"  Roles buscados: {', '.join(profile.target_roles)}")
    console.print(f"  Skills: {', '.join(profile.hard_skills[:5])}...")


def cmd_search():
    """Inicia una búsqueda de vacantes."""
    manager = ProfileManager()
    profiles = manager.list_profiles()

    if not profiles:
        console.print("[red]No tenés ningún perfil configurado. Ejecutá: python main.py setup[/red]")
        return

    # Seleccionar perfil
    if len(profiles) == 1:
        profile_name = profiles[0]
    else:
        profile_name = Prompt.ask("Perfil a usar", choices=profiles, default=profiles[0])

    profile = manager.load(profile_name)
    console.print(f"[green]Perfil: {profile.full_name}[/green]")

    # Cargar config guardada o configurar
    config_path = Path("data/last_search_config.json")
    if config_path.exists() and Confirm.ask("¿Usar la última configuración de búsqueda?", default=True):
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
        config = SearchConfig(
            keywords=data["keywords"],
            location=data.get("location", "Argentina"),
            portals=[Portal(p) for p in data.get("portals", ["computrabajo"])],
            min_relevance_score=data.get("min_relevance_score", 0.65),
            max_results_per_portal=data.get("max_results_per_portal", 30),
            auto_apply=data.get("auto_apply", False),
        )
    else:
        # Configuración interactiva
        keywords_raw = Prompt.ask(
            "Keywords de búsqueda (separadas por coma)",
            default=", ".join(profile.target_roles[:2]),
        )
        keywords = [k.strip() for k in keywords_raw.split(",")]

        location = Prompt.ask("Ubicación", default="Argentina")

        console.print("\nPortales disponibles: computrabajo, bumeran, indeed")
        portals_raw = Prompt.ask("Portales (separados por coma)", default="computrabajo,bumeran")
        portals = [Portal(p.strip()) for p in portals_raw.split(",")]

        min_score = float(Prompt.ask("Score mínimo (0.0 - 1.0)", default="0.65"))
        max_results = int(Prompt.ask("Máximo de resultados por portal", default="30"))
        auto_apply = Confirm.ask("¿Aplicar automáticamente sin confirmación?", default=False)

        config = SearchConfig(
            keywords=keywords,
            location=location,
            portals=portals,
            min_relevance_score=min_score,
            max_results_per_portal=max_results,
            auto_apply=auto_apply,
        )

    # Ejecutar agente
    agent = JobAgent()
    asyncio.run(agent.run(profile, config, interactive=not config.auto_apply))


def cmd_dashboard():
    """Abre el dashboard web."""
    import subprocess
    dashboard_path = Path(__file__).parent / "dashboard" / "app.py"
    console.print("[blue]Iniciando dashboard en http://localhost:8501[/blue]")
    subprocess.run(["streamlit", "run", str(dashboard_path)])


def cmd_stats():
    """Muestra estadísticas rápidas."""
    from modules.tracker import ApplicationTracker
    tracker = ApplicationTracker()
    stats = tracker.get_stats()

    console.rule("[bold]Estadísticas JobAgent[/bold]")
    console.print(f"Vacantes scrapeadas:   {stats['total_jobs_scraped']}")
    console.print(f"Aplicaciones totales:  {stats['total_applications']}")
    console.print(f"Score promedio:        {stats['avg_relevance_score']:.0%}")
    console.print("\nPor estado:")
    for status, count in stats.get("by_status", {}).items():
        console.print(f"  {status:15s}: {count}")


COMMANDS = {
    "setup": cmd_setup,
    "search": cmd_search,
    "dashboard": cmd_dashboard,
    "stats": cmd_stats,
}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else None

    if cmd not in COMMANDS:
        console.print("[bold]JobAgent LATAM[/bold] — Agente de IA para búsqueda de empleo\n")
        console.print("Comandos disponibles:")
        console.print("  [cyan]python main.py setup[/cyan]      → Configurar tu perfil desde el CV")
        console.print("  [cyan]python main.py search[/cyan]     → Buscar y aplicar a vacantes")
        console.print("  [cyan]python main.py dashboard[/cyan]  → Abrir dashboard web")
        console.print("  [cyan]python main.py stats[/cyan]      → Ver estadísticas")
        sys.exit(0)

    COMMANDS[cmd]()
