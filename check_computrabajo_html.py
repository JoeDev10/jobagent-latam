import asyncio
import sys
sys.path.insert(0, '.')
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

URL = "https://ar.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-analista-qa-ssr-en-san-nicolas-6310ABF5C14B520761373E686DCF3405"

SEARCH_URL = "https://ar.computrabajo.com/trabajo-de-desarrollador-python"


async def check():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = await b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="es-AR",
        )
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        page = await ctx.new_page()

        # --- Detalle ---
        await page.goto(URL, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        print("=== H2/H3 encontrados ===")
        for tag in soup.find_all(["h2", "h3"]):
            t = tag.get_text(strip=True)
            if t:
                print(f"  <{tag.name} class={tag.get('class')}> {t[:80]}")

        print("\n=== DIVS con texto largo (>200 chars) ===")
        seen = set()
        for div in soup.find_all("div"):
            txt = div.get_text(separator=" ", strip=True)
            cls = str(div.get("class"))
            if len(txt) > 200 and cls not in seen and div.get("class"):
                seen.add(cls)
                print(f"  class={div.get('class')} id={div.get('id')} len={len(txt)}")
                print(f"    preview: {txt[:120]}")

        # --- Listado ---
        print("\n=== LISTADO (search page) ===")
        await page.goto(SEARCH_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        html2 = await page.content()
        soup2 = BeautifulSoup(html2, "lxml")

        articles = soup2.select("article.box_offer")
        print(f"article.box_offer encontrados: {len(articles)}")
        for art in articles[:3]:
            link = art.select_one("a.js-o-link")
            print(f"  a.js-o-link: {link.get_text(strip=True)[:50] if link else 'NO ENCONTRADO'}")
            print(f"    href: {link.get('href','')[:80] if link else ''}")

        await b.close()


asyncio.run(check())
