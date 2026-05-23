"""Login manual con inspección detallada de cada paso."""
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
from playwright_stealth import Stealth

from core.config import settings

SHOTS = Path(__file__).parent / "data" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)
COOKIES_PATH = Path(__file__).parent / "data" / "sessions" / "computrabajo.json"
COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)


async def main():
    print(f"Email: {settings.computrabajo_email}")
    print(f"Pass:  {'*' * len(settings.computrabajo_password)} ({len(settings.computrabajo_password)} chars)\n")

    async with Stealth().use_async(async_playwright()) as pw:
        browser = await pw.chromium.launch(
            headless=False,
            slow_mo=120,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
        )
        page = await context.new_page()

        # 1. Home → click Iniciar sesión
        print("1. Yendo al home...")
        await page.goto("https://ar.computrabajo.com/", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        print("2. Clickeando 'Iniciar sesión'...")
        clicked = False
        for sel in ['a[href*="acceso"]', 'a:has-text("Iniciar sesión")', 'a:has-text("Ingresar")']:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.click()
                    clicked = True
                    print(f"   click con: {sel}")
                    break
            except Exception:
                pass

        if not clicked:
            print("   FAIL: no encontré el link")
            return

        await page.wait_for_load_state("networkidle", timeout=15000)
        await asyncio.sleep(2)
        print(f"   URL ahora: {page.url[:100]}\n")

        # Screenshot pre-fill
        await page.screenshot(path=str(SHOTS / "01_login_form.png"), full_page=True)

        # 2. Llenar email
        print("3. Llenando email...")
        await page.fill('input[name="Email"]', settings.computrabajo_email)
        await asyncio.sleep(1)

        print("4. Llenando password...")
        await page.fill('input[name="Password"]', settings.computrabajo_password)
        await asyncio.sleep(1)

        await page.screenshot(path=str(SHOTS / "02_filled.png"), full_page=True)

        # 3. Click Continuar
        print("5. Clickeando Continuar...")
        await page.click('button:has-text("Continuar")')

        # Esperar respuesta
        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        await page.screenshot(path=str(SHOTS / "03_after_submit.png"), full_page=True)
        print(f"\n   URL después de submit: {page.url[:100]}")

        # Buscar mensaje de error
        errors = await page.evaluate("""
            () => {
                const sels = ['.field-validation-error', '.validation-summary-errors',
                              '[class*="error"]', '[class*="alert"]', '.help-block',
                              '.invalid-feedback', '[role="alert"]'];
                const out = [];
                sels.forEach(s => document.querySelectorAll(s).forEach(e => {
                    const t = (e.innerText || '').trim();
                    if (t && t.length < 300) out.push(`${s}: ${t}`);
                }));
                return [...new Set(out)];
            }
        """)
        if errors:
            print("\n=== Errores en la página ===")
            for e in errors:
                print(f"  {e}")
        else:
            print("\n(no se encontraron mensajes de error visibles)")

        # Estado de login
        print(f"\n6. URL final: {page.url[:120]}")
        if "Account/Login" in page.url or "account/login" in page.url:
            print("   ✗ Aún en login")
        else:
            print("   ✓ Salió del login — guardando cookies")
            cookies = await context.cookies()
            COOKIES_PATH.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"   {len(cookies)} cookies guardadas en {COOKIES_PATH.name}")

        print("\n[Navegador queda 30s — inspeccioná manualmente lo que necesites]")
        await asyncio.sleep(30)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
