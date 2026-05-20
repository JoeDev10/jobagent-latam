import asyncio, sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

DETAIL_URL = "https://ar.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-analista-qa-ssr-en-san-nicolas-6310ABF5C14B520761373E686DCF3405"

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="es-AR",
        )
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        page = await ctx.new_page()
        await page.goto(DETAIL_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        # Bloque principal alrededor del h1
        h1 = soup.select_one("h1.fs24")
        if h1:
            parent = h1.find_parent("div") or h1.find_parent("section") or h1.find_parent("article")
            if parent:
                print("=== BLOQUE PADRE DEL H1 ===")
                print(parent.prettify()[:2000])

        # Buscar descripción: el div después de h3 "Descripción"
        h3_desc = soup.find("h3", string=lambda t: t and "escripci" in t)
        if h3_desc:
            print("\n=== BLOQUE DESCRIPCIÓN ===")
            sib = h3_desc.find_next_sibling()
            while sib and len(sib.get_text(strip=True)) < 50:
                sib = sib.find_next_sibling()
            if sib:
                print(f"Tag: <{sib.name} class={sib.get('class')} id={sib.get('id')}>")
                print(sib.get_text(strip=True)[:300])

        await browser.close()

asyncio.run(check())
