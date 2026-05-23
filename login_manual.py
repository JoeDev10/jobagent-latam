"""
Login manual asistido v2 — usa un perfil persistente de Chrome.
Mucho más difícil de detectar por anti-bots como Computrabajo.

Cómo funciona:
- Usa tu Chrome real (channel='chrome')
- Crea un perfil persistente en data/chrome_profile/ (queda guardado)
- La primera vez te logueás manual. Las próximas, las cookies se cargan
  automáticamente del perfil.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright

ROOT = Path(__file__).parent
PROFILE_DIR = ROOT / "data" / "chrome_profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
COOKIES_PATH = ROOT / "data" / "sessions" / "computrabajo.json"
COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)


async def wait_for_enter(prompt=""):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, input, prompt)


async def main():
    print("=" * 60)
    print("  LOGIN MANUAL EN COMPUTRABAJO (Chrome con perfil persistente)")
    print("=" * 60)
    print()
    print(f"Perfil: {PROFILE_DIR}")
    print()
    print("Va a abrir tu Chrome real. Logueate de forma normal:")
    print("  1. NO uses 'Continúa con Google' (Google bloquea automatización)")
    print(f"  2. Usá email + password: joeltrainer99@gmail.com / trainer7")
    print("  3. Cuando estés logueado, volvé acá y presioná ENTER")
    print()
    await wait_for_enter("Presioná ENTER para abrir Chrome...")

    async with async_playwright() as pw:
        # launch_persistent_context = Chrome real con perfil que persiste en disco
        try:
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                channel="chrome",  # usa tu Chrome instalado
                headless=False,
                viewport={"width": 1366, "height": 768},
                locale="es-AR",
                timezone_id="America/Argentina/Buenos_Aires",
                args=[
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            print("(Chrome real + perfil persistente)")
        except Exception as e:
            print(f"Falló Chrome real: {e}")
            print("Probando con Chromium...")
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )

        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://ar.computrabajo.com/")

        print()
        print("→ Logueate ahora con email + password.")
        print("→ Cuando veas tu nombre/foto arriba, volvé y presioná ENTER.")
        print()
        await wait_for_enter()

        # Verificar logueado ANTES de cerrar
        cookies = await context.cookies()
        # Buscar evidencia de auth
        auth_cookies = [c for c in cookies if any(k in c["name"].lower() for k in [
            "auth", "identity", "session", "idsrv", "aspxauth", "token", "login"
        ]) and "correlation" not in c["name"].lower() and "asp.net_sessionid" != c["name"].lower()]

        # También verificar visitando /candidato/cv
        await page.goto("https://ar.computrabajo.com/candidato/cv", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        body = await page.evaluate("() => (document.body.innerText || '').slice(0, 2000).toLowerCase()")
        logged_signals = sum(1 for s in ["cerrar sesi", "mi cuenta", "mis postulaciones", "mi perfil"] if s in body)

        print(f"\nCookies totales: {len(cookies)}")
        print(f"Cookies de auth detectadas: {len(auth_cookies)}")
        if auth_cookies:
            for c in auth_cookies[:5]:
                print(f"  - {c['name']} @ {c['domain']}")
        print(f"Señales de sesión en página: {logged_signals}/4")

        if logged_signals >= 1 or len(auth_cookies) >= 1:
            COOKIES_PATH.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\n✓ SESIÓN VÁLIDA — cookies guardadas en {COOKIES_PATH.name}")
        else:
            print(f"\n✗ NO SE DETECTÓ SESIÓN. URL actual: {page.url}")
            print("  Probablemente no completaste el login. Probá de nuevo.")

        print("\n[5s y cierro]")
        await asyncio.sleep(5)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
