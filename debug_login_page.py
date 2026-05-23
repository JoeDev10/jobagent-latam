"""
Diagnóstico v2: navega a una vacante, clickea 'Postularme' (sin estar logueado)
para que Computrabajo nos lleve a la URL real de login, y la inspecciona.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright

from modules.tracker import ApplicationTracker
from core import ApplicationStatus


async def main():
    tracker = ApplicationTracker()
    pendientes = tracker.get_applications(status=ApplicationStatus.PENDING)
    target = next(
        (p for p in pendientes if p.get("portal") == "computrabajo" and (p.get("relevance_score") or 0) >= 0.8),
        None,
    )
    if not target:
        print("No hay pendiente de Computrabajo")
        return

    url_vacante = target["url"]
    print(f"Yendo a vacante: {url_vacante}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=80)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(url_vacante, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(2)

        # Click "Postularme"
        try:
            await page.click('a.b_primary:has-text("Postularme")', timeout=5000)
        except Exception as e:
            print(f"No pude clickear Postularme: {e}")
            return

        # Esperar el redirect
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(3)

        print(f"=== URL LOGIN: {page.url} ===\n")

        # En la página de login (o modal): listar inputs / botones
        # Probar tanto en el frame principal como en frames hijos
        for f_idx, frame in enumerate([page.main_frame] + page.frames):
            if frame == page.main_frame and f_idx > 0:
                continue
            print(f"--- Frame {f_idx} ({frame.url[:80]}) ---")
            try:
                inputs = await frame.evaluate("""
                    () => Array.from(document.querySelectorAll('input')).map(i => ({
                        type: i.type, name: i.name, id: i.id, placeholder: i.placeholder,
                        visible: i.offsetParent !== null,
                        class: (i.className && i.className.toString) ? i.className.toString().slice(0,50) : '',
                    }))
                """)
                for i in inputs:
                    v = "✓" if i["visible"] else "✗"
                    print(f"  INPUT [{v}] type={i['type']:8s} name='{i['name']}' id='{i['id']}' placeholder='{i['placeholder']}'")

                buttons = await frame.evaluate("""
                    () => Array.from(document.querySelectorAll('button, input[type="submit"]')).map(b => ({
                        text: (b.innerText || b.value || '').trim().slice(0,50),
                        type: b.type, id: b.id,
                        class: (b.className && b.className.toString) ? b.className.toString().slice(0,50) : '',
                        visible: b.offsetParent !== null,
                    }))
                """)
                for b in buttons:
                    v = "✓" if b["visible"] else "✗"
                    print(f"  BTN   [{v}] '{b['text']}' type={b['type']}")
            except Exception as e:
                print(f"  (error inspeccionando frame: {e})")

        shot = Path(__file__).parent / "data" / "screenshots" / "debug_login_v2.png"
        await page.screenshot(path=str(shot), full_page=True)
        print(f"\nScreenshot: {shot}")

        print("\n[20s para inspección]")
        await asyncio.sleep(20)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
