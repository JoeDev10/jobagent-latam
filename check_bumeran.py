import asyncio, sys, json, re
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

BASE = "https://www.bumeran.com.ar"
DETAIL = "https://www.bumeran.com.ar/empleos/qa-automation-grupo-petersen-1118282244.html"

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="es-AR",
        )
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        page = await ctx.new_page()
        await page.goto(DETAIL, wait_until="domcontentloaded")
        await asyncio.sleep(4)
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        ld_scripts = soup.find_all("script", type="application/ld+json")
        print(f"JSON-LD scripts: {len(ld_scripts)}")

        job_data = {}
        company_data = {}
        for script in ld_scripts:
            try:
                data = json.loads(script.string or "{}")
                if "title" in data and "description" in data:
                    job_data = data
                if data.get("@type") == "LocalBusiness":
                    company_data = data
            except:
                pass

        print(f"\n=== JOB DATA keys: {list(job_data.keys())} ===")
        print(f"title: {job_data.get('title','')}")
        print(f"description (primeros 200 chars): {re.sub('<[^>]+>', '', job_data.get('description',''))[:200]}")
        print(f"salary: {job_data.get('salary', job_data.get('baseSalary','N/A'))}")

        print(f"\n=== COMPANY DATA ===")
        print(f"name: {company_data.get('name','')}")
        print(f"address: {company_data.get('address','')}")
        print(f"url: {company_data.get('url','')[:60]}")

        # Ubicación desde h2 que la contiene
        for h2 in soup.find_all("h2"):
            txt = h2.get_text(strip=True)
            if "Argentina" in txt or "Buenos Aires" in txt:
                print(f"\n=== UBICACIÓN (h2) ===\n  {txt}")
                break

        # Probar el listado con la URL correcta
        print("\n=== PROBANDO LISTADO ===")
        await page.goto(f"{BASE}/empleos-busqueda-qa.html", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        html2 = await page.content()
        soup2 = BeautifulSoup(html2, "lxml")
        empleo_links = list({
            a.get("href","").split("?")[0]: a.get_text(strip=True)
            for a in soup2.find_all("a", href=True)
            if "/empleos/" in a.get("href","") and len(a.get_text(strip=True)) > 10
        }.items())
        print(f"Vacantes únicas encontradas: {len(empleo_links)}")
        for href, titulo in empleo_links[:5]:
            print(f"  {titulo[:50]} → {href[:70]}")

        await browser.close()

asyncio.run(check())
