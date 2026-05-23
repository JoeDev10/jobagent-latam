"""
Aplica a las pendientes con score >= 0.80 usando el Chrome real del usuario
(via CDP). Esto evita la detección anti-bot porque ES tu Chrome real.

Requisitos previos:
  1. python chrome_launcher.py     # abre Chrome en modo debug
  2. (logueate manualmente la primera vez en Computrabajo en esa ventana)
  3. python aplicar_pendientes.py  # este script
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console

from core import ApplicationStatus, get_logger
from modules.applicator import ApplicationBot
from modules.tracker import ApplicationTracker
from modules.profile import ProfileManager
from modules.notifier import TelegramNotifier

logger = get_logger(__name__)
console = Console(legacy_windows=False)

THRESHOLD = 0.80
SKIP_PORTALS = {"bumeran"}  # sin credenciales en .env
CDP_URL = "http://localhost:9223"
RETRY_PER_VACANCY = 1  # 1 reintento por vacante


async def check_cdp_available() -> bool:
    """Chequea si hay un Chrome con CDP escuchando."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(("127.0.0.1", 9222)) == 0
    except Exception:
        return False


async def verify_session(bot: ApplicationBot) -> bool:
    """Navega a la home de Computrabajo y verifica que haya sesión activa."""
    page = await bot.new_page()
    try:
        await page.goto("https://ar.computrabajo.com/", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)
        url = page.url.lower()
        if "acceso" in url or "login" in url or "account/login" in url:
            return False
        body = await page.evaluate("() => (document.body.innerText || '').slice(0, 3000).toLowerCase()")
        logged_in_signals = [
            "notificaciones", "cerrar sesi", "mi cuenta",
            "mis postulaciones", "mi perfil", "mi cv",
        ]
        logged_out_signals = ["iniciar sesi", "ingresar", "crea tu cuenta gratis"]
        # Nombre del usuario en el header es señal fuerte
        has_name = await page.evaluate(
            "() => !!document.querySelector('nav, header, [class*=nav], [class*=header]')"
            " && (document.querySelector('nav, header, [class*=nav], [class*=header]')"
            ".innerText || '').length > 0"
        )
        pos = sum(1 for s in logged_in_signals if s in body)
        neg = sum(1 for s in logged_out_signals if s in body)
        if pos >= 1:
            return True
        if neg >= 1 and pos == 0:
            return False
        return True
    except Exception as e:
        logger.warning(f"verify_session error: {e}")
        return False
    finally:
        await page.close()


async def apply_one_with_retry(bot: ApplicationBot, full_app, tracker, notifier) -> str:
    """Aplica con 1 reintento. Devuelve estado final como string."""
    for attempt in range(1, RETRY_PER_VACANCY + 2):
        try:
            result = await bot.apply(full_app)
            tracker.update_status(result.id, result.status, result.notes)
            if result.status == ApplicationStatus.APPLIED:
                try:
                    await notifier.notify_applied(result)
                except Exception as e:
                    logger.warning(f"Telegram: {e}")
                return "aplicada"
            elif attempt < RETRY_PER_VACANCY + 1:
                console.print(f"   [yellow]Intento {attempt} falló ({result.notes}). Reintentando en 5s...[/yellow]")
                await asyncio.sleep(5)
            else:
                return f"fallo: {result.notes or 'sin info'}"
        except Exception as e:
            logger.error(f"Excepción aplicando: {e}")
            if attempt < RETRY_PER_VACANCY + 1:
                await asyncio.sleep(5)
            else:
                tracker.update_status(full_app.id, ApplicationStatus.DISCARDED, notes=f"Error: {str(e)[:200]}")
                return f"error: {str(e)[:80]}"
    return "fallo"


async def main(dry_run: bool):
    tracker = ApplicationTracker()
    profile_mgr = ProfileManager()
    notifier = TelegramNotifier()

    profile = profile_mgr.load("marcelo")
    if not profile:
        console.print("[red]No se encontró el perfil 'marcelo'[/red]")
        sys.exit(1)

    # 1. Verificar que Chrome con CDP esté abierto
    if not await check_cdp_available():
        console.print("[red]No hay Chrome de debug corriendo en localhost:9222.[/red]\n")
        console.print("Antes de correr este script:")
        console.print("  1. [cyan]python chrome_launcher.py[/cyan]")
        console.print("  2. Logueate manualmente en Computrabajo (primera vez)")
        console.print("  3. Volvé a correr [cyan]python aplicar_pendientes.py[/cyan]")
        sys.exit(1)

    console.print("[green]✓[/green] Chrome de debug disponible\n")

    # 2. Cargar pendientes
    pendientes = tracker.get_applications(status=ApplicationStatus.PENDING)
    para_aplicar = [p for p in pendientes
                    if (p.get("relevance_score") or 0) >= THRESHOLD
                    and p.get("portal") not in SKIP_PORTALS]
    saltadas_bumeran = [p for p in pendientes
                        if p.get("portal") in SKIP_PORTALS
                        and (p.get("relevance_score") or 0) >= THRESHOLD]
    descartar = [p for p in pendientes if (p.get("relevance_score") or 0) < THRESHOLD]

    console.rule(f"[bold]Aplicar pendientes — modo CDP ({'DRY-RUN' if dry_run else 'REAL'})[/bold]")
    console.print(f"Aplicar:        {len(para_aplicar)}")
    console.print(f"Saltar Bumeran: {len(saltadas_bumeran)}")
    console.print(f"Descartar:      {len(descartar)}\n")

    if not para_aplicar:
        console.print("[yellow]No hay nada para aplicar.[/yellow]")
        return

    # 3. Descartar las de bajo score
    if not dry_run:
        for p in descartar:
            tracker.update_status(p["id"], ApplicationStatus.DISCARDED, notes="Score < 80%")

    # 4. Conectar al Chrome via CDP y verificar sesión
    async with ApplicationBot(cdp_url=CDP_URL) as bot:
        console.print("Verificando sesión en Computrabajo...")
        ok = await verify_session(bot)
        if not ok:
            console.print("[red]✗ NO estás logueado en Computrabajo en el Chrome de debug.[/red]")
            console.print("Andá a la ventana de Chrome que abrió chrome_launcher.py,")
            console.print("logueate manualmente, y volvé a correr este script.")
            return
        console.print("[green]✓[/green] Sesión activa\n")

        if dry_run:
            console.print("[yellow][DRY-RUN] Hasta acá llegó. No aplico de verdad.[/yellow]")
            return

        # 5. Aplicar a cada vacante
        resultados = {"aplicada": 0, "fallo": 0, "error": 0}
        for i, p in enumerate(para_aplicar, 1):
            console.rule(f"[cyan]{i}/{len(para_aplicar)}[/cyan]  {p.get('title','?')[:60]}")
            console.print(f"   {p.get('company','?')} ({p.get('portal')}) — score {(p.get('relevance_score') or 0):.0%}")

            full = tracker.get_application_full(p["id"], profile=profile)
            if not full:
                resultados["error"] += 1
                continue

            estado = await apply_one_with_retry(bot, full, tracker, notifier)
            if estado == "aplicada":
                resultados["aplicada"] += 1
                console.print("   [green]✓ Aplicada[/green]")
            elif estado.startswith("error"):
                resultados["error"] += 1
                console.print(f"   [red]✗ {estado}[/red]")
            else:
                resultados["fallo"] += 1
                console.print(f"   [yellow]⚠ {estado}[/yellow]")

            await asyncio.sleep(2)  # respiro entre vacantes

    # 6. Resumen
    console.rule("[bold green]Resumen[/bold green]")
    console.print(f"Aplicadas: {resultados['aplicada']}")
    console.print(f"Fallidas:  {resultados['fallo']}")
    console.print(f"Errores:   {resultados['error']}")
    console.print(f"Descartadas (score bajo): {len(descartar)}")
    console.print(f"Bumeran saltadas:         {len(saltadas_bumeran)}")

    try:
        await notifier.notify_daily_summary({
            "total_jobs_scraped": 0,
            "total_applications": resultados["aplicada"],
            "avg_relevance_score": 0.85,
            "by_status": {
                "aplicada": resultados["aplicada"],
                "descartada": len(descartar) + resultados["error"],
                "pendiente": resultados["fallo"] + len(saltadas_bumeran),
            },
        })
    except Exception as e:
        logger.warning(f"Telegram resumen: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Verifica todo sin aplicar")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
