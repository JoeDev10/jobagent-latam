"""
Test end-to-end: scrapea 2 vacantes de cada portal y muestra los datos.

Uso:
  python check_scraper_live.py                  # prueba Computrabajo + Bumeran
  python check_scraper_live.py computrabajo     # solo Computrabajo
  python check_scraper_live.py bumeran          # solo Bumeran
  python check_scraper_live.py zonajobs         # solo ZonaJobs
  python check_scraper_live.py indeed           # solo Indeed
"""
import asyncio
import sys
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from core import SearchConfig, Portal

console = Console(legacy_windows=False)

SCRAPER_MAP = {
    "computrabajo": ("modules.scrapers.computrabajo", "ComputrabajoScraper"),
    "bumeran":      ("modules.scrapers.bumeran",      "BumeranScraper"),
    "zonajobs":     ("modules.scrapers.zonajobs",      "ZonaJobsScraper"),
    "indeed":       ("modules.scrapers.indeed",        "IndeedScraper"),
}


async def test_scraper(portal_name, keyword="desarrollador python", max_results=2):
    import importlib

    if portal_name not in SCRAPER_MAP:
        console.print(f"[red]Portal desconocido: {portal_name}[/red]")
        return 0

    mod_path, cls_name = SCRAPER_MAP[portal_name]
    mod = importlib.import_module(mod_path)
    scraper_cls = getattr(mod, cls_name)

    config = SearchConfig(
        keywords=[keyword],
        location="Argentina",
        portals=[Portal(portal_name)],
        max_results_per_portal=max_results,
        min_relevance_score=0.0,
    )

    console.rule(f"[bold cyan]{portal_name.upper()}[/bold cyan] | keyword: '{keyword}'")

    count = 0
    try:
        async with scraper_cls() as scraper:
            async for job in scraper.search(config):
                count += 1
                console.print(f"\n[bold][{count}] {job.title}[/bold]")
                console.print(f"  Empresa:   {job.company}")
                console.print(f"  Ubicacion: {job.location}")
                console.print(f"  Modalidad: {job.modality}")
                console.print(f"  Salario:   {job.salary_range or 'No especificado'}")
                console.print(f"  URL:       {job.url[:80]}")
                desc_preview = job.description[:200].replace("\n", " ").strip()
                console.print(f"  Desc:      {desc_preview}...")
                console.print(f"  Requisitos: {len(job.requirements)} items")
                if count >= max_results:
                    break
    except Exception as e:
        console.print(f"[red]Error en {portal_name}: {e}[/red]")
        import traceback
        traceback.print_exc()

    console.print(f"\n[green]Total scrapeadas de {portal_name}: {count}[/green]")
    return count


async def main():
    portals_to_test = sys.argv[1:] if len(sys.argv) > 1 else ["computrabajo", "bumeran"]
    keyword = "desarrollador python"
    total = 0

    for portal in portals_to_test:
        n = await test_scraper(portal, keyword=keyword, max_results=2)
        total += (n or 0)
        await asyncio.sleep(2)

    console.rule("[bold]Resumen final[/bold]")
    console.print(f"Total vacantes obtenidas: {total}")


if __name__ == "__main__":
    asyncio.run(main())
