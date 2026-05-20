"""
Dry run: scraping + scoring + cartas, sin aplicar a ninguna vacante.
Sirve para verificar end-to-end el pipeline antes de hacer aplicaciones reales.
Todo se guarda en la DB como pendiente para revisión manual luego.
"""
import asyncio
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

from modules.profile import ProfileManager
from core import Portal, JobModality, SearchConfig
from core.agent import JobAgent

manager = ProfileManager()
profile = manager.load("marcelo")
if not profile:
    print("No se encontró el perfil 'marcelo'")
    sys.exit(1)

config = SearchConfig(
    keywords=["QA Analyst", "QA Tester", "QA Manual"],
    location="Argentina",
    portals=[Portal.COMPUTRABAJO],
    modality=JobModality.ANY,
    max_results_per_portal=5,
    min_relevance_score=0.60,
    auto_apply=False,
)

agent = JobAgent()
asyncio.run(agent.run(profile, config, interactive=False))
