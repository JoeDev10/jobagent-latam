from .base import BaseScraper
from .computrabajo import ComputrabajoScraper
from .bumeran import BumeranScraper
from .indeed import IndeedScraper
from .zonajobs import ZonaJobsScraper
from core import Portal


SCRAPER_MAP = {
    Portal.COMPUTRABAJO: ComputrabajoScraper,
    Portal.BUMERAN: BumeranScraper,
    Portal.INDEED: IndeedScraper,
    Portal.ZONAJOBS: ZonaJobsScraper,
}


def get_scraper(portal: Portal) -> BaseScraper:
    cls = SCRAPER_MAP.get(portal)
    if not cls:
        raise ValueError(f"No hay scraper disponible para {portal}")
    return cls()


__all__ = [
    "BaseScraper", "ComputrabajoScraper", "BumeranScraper",
    "IndeedScraper", "ZonaJobsScraper", "SCRAPER_MAP", "get_scraper",
]
