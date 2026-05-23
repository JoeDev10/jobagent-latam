"""
Diagnóstico: abre una URL de Computrabajo con Playwright directo y lista
los botones / links candidatos a 'Aplicar / Postular / Inscribirme'.
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

from modules.tracker import ApplicationTracker
from core import ApplicationStatus

ROOT = Path(__file__).parent
SCREEN_DIR = ROOT / "data" / "screenshots"
SCREEN_DIR.mkdir(parents=True, exist_ok=True)
COOKIES_PATH = ROOT / "data" / "sessions" / "computrabajo.json"


async def main():
    tracker = ApplicationTracker()
    pendientes = tracker.get_applications(status=ApplicationStatus.PENDING)
    target = next(
        (p for p in pendientes if p.get("portal") == "computrabajo" and (p.get("relevance_score") or 0) >= 0.8),
        None,
    )
    if not target:
        print("No hay vacantes Computrabajo pendientes >= 80%")
        return

    url = target["url"]
    print(f"Diagnosticando: {target['title']}")
    print(f"URL: {url}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=80)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
        )

        # Cargar cookies si existen
        if COOKIES_PATH.exists():
            cookies = json.loads(COOKIES_PATH.read_text(encoding="utf-8"))
            await context.add_cookies(cookies)
            print(f"✓ {len(cookies)} cookies cargadas\n")
        else:
            print("⚠ No hay cookies guardadas — vas a tener que loguearte manual\n")

        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(5)  # esperar JS

        # Screenshot
        shot = SCREEN_DIR / "debug_computrabajo.png"
        await page.screenshot(path=str(shot), full_page=True)
        print(f"Screenshot: {shot}\n")

        # Detectar todos los candidatos a botón "aplicar"
        print("=== Candidatos a botón Aplicar/Postular/Inscribir ===")
        candidatos = await page.evaluate("""
            () => {
                const txt = e => (e.innerText || e.textContent || '').trim().slice(0, 80);
                const items = [];
                document.querySelectorAll('a, button, input[type="button"], input[type="submit"], div[role="button"], span[role="button"]').forEach(e => {
                    const text = txt(e).toLowerCase();
                    if (/aplicar|postular|inscribir|enviar.*cv|enviar.*postulaci/.test(text)) {
                        const rect = e.getBoundingClientRect();
                        items.push({
                            tag: e.tagName,
                            text: txt(e),
                            id: e.id || '',
                            classes: (e.className && e.className.toString) ? e.className.toString().slice(0, 80) : '',
                            href: e.href || '',
                            visible: rect.width > 0 && rect.height > 0,
                        });
                    }
                });
                return items;
            }
        """)
        if not candidatos:
            print("  (ninguno encontrado)")
        for c in candidatos:
            vis = "✓" if c['visible'] else "✗"
            print(f"  [{vis}] <{c['tag']}> text='{c['text']}'")
            print(f"      id='{c['id']}' class='{c['classes']}'")
            if c.get('href'):
                print(f"      href={c['href'][:120]}")

        # Estado de sesión
        print("\n=== Estado de sesión ===")
        sesion = await page.evaluate("""
            () => {
                const t = document.body.innerText.toLowerCase();
                return {
                    has_login_link: /iniciar\\s*sesi[oó]n|ingresar/.test(t),
                    has_user_menu: /cerrar\\s*sesi[oó]n|mi\\s*cuenta|mis\\s*postulaciones/.test(t),
                };
            }
        """)
        print(f"  'Iniciar sesión' visible: {sesion['has_login_link']}")
        print(f"  Menú usuario visible:     {sesion['has_user_menu']}")

        print("\n[Dejo el navegador abierto 20s para inspección manual]")
        await asyncio.sleep(20)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
