"""
Prueba de login en Computrabajo y Bumeran.
Abre el navegador visible para que puedas ver qué pasa.
NO aplica a ninguna vacante.
"""
import asyncio
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright
from core import settings, get_logger
from modules.auth import LoginManager

logger = get_logger(__name__)


async def test_login(portal: str):
    print(f"\n{'='*50}")
    print(f"Probando login en: {portal.upper()}")
    print("="*50)

    if not LoginManager().has_credentials(portal):
        print(f"  [ERROR] Faltan credenciales en .env:")
        print(f"  Agrega {portal.upper()}_EMAIL y {portal.upper()}_PASSWORD")
        return False

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # visible siempre en este test
            slow_mo=100,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="es-AR",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        manager = LoginManager()
        success = await manager.ensure_logged_in(context, portal)

        if success:
            print(f"\n  LOGIN EXITOSO en {portal}")
            print(f"  Cookies guardadas en data/sessions/{portal}.json")
            print(f"  El navegador se va a cerrar en 5 segundos...")
            await asyncio.sleep(5)
        else:
            print(f"\n  LOGIN FALLIDO en {portal}")
            print(f"  El navegador queda abierto 15s para que veas el error...")
            await asyncio.sleep(15)

        await browser.close()
        return success


async def main():
    print("JobAgent LATAM — Test de Login")
    print("El navegador se va a abrir. Vas a ver el proceso de login en vivo.")

    portals_to_test = []
    if settings.computrabajo_email:
        portals_to_test.append("computrabajo")
    if settings.bumeran_email:
        portals_to_test.append("bumeran")

    if not portals_to_test:
        print("\n[ERROR] No hay credenciales en .env")
        print("Abre el archivo .env y completa:")
        print("  COMPUTRABAJO_EMAIL=tu@email.com")
        print("  COMPUTRABAJO_PASSWORD=tu_password")
        return

    results = {}
    for portal in portals_to_test:
        results[portal] = await test_login(portal)

    print("\n" + "="*50)
    print("RESUMEN:")
    for portal, ok in results.items():
        status = "OK" if ok else "FALLO"
        print(f"  {portal}: {status}")

    if all(results.values()):
        print("\nTodo OK. Ahora podes correr run_search.py")
    else:
        print("\nAlgunos logins fallaron. Revisá las credenciales en .env")


asyncio.run(main())
