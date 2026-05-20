"""
Scraper para Bumeran Argentina (bumeran.com.ar)

Estrategia de extracción:
  1. JSON-LD con @type = JobPosting (fuente primaria — muy estable)
  2. Meta tags OG / schema.org
  3. Selectores CSS con múltiples fallbacks
"""
import json
import re
import uuid
from typing import AsyncGenerator

from bs4 import BeautifulSoup

from core import JobListing, JobModality, Portal, SearchConfig, get_logger
from .base import BaseScraper

logger = get_logger(__name__)

BASE_URL = "https://www.bumeran.com.ar"


class BumeranScraper(BaseScraper):
    portal_name = "bumeran"

    # ─── Búsqueda ─────────────────────────────────────────────────────────────

    async def search(self, config: SearchConfig) -> AsyncGenerator[JobListing, None]:
        page = await self.new_page()

        for keyword in config.keywords:
            logger.info(f"[Bumeran] Buscando: '{keyword}'")
            results_found = 0
            page_num = 1
            prev_urls: set[str] = set()

            while results_found < config.max_results_per_portal:
                current_url = self._build_search_url(keyword, page_num)
                try:
                    await self.safe_goto(page, current_url)
                except Exception as e:
                    logger.error(f"[Bumeran] Fallo cargando página {page_num}: {e}")
                    break

                await self.human_delay(2, 4)
                await self.random_scroll(page, 200, 600)

                html = await page.content()
                listings = self._parse_listings(html)

                if not listings:
                    logger.info(f"[Bumeran] Sin resultados en página {page_num}")
                    break

                page_urls = {l["url"] for l in listings}
                if page_urls and page_urls == prev_urls:
                    logger.info(f"[Bumeran] Página {page_num} repite — fin de resultados")
                    break
                prev_urls = page_urls

                for listing in listings:
                    if results_found >= config.max_results_per_portal:
                        break
                    try:
                        detail = await self.get_job_detail(listing["url"])
                        results_found += 1
                        yield detail
                        await self.human_delay(1, 2.5)
                    except Exception as e:
                        logger.warning(f"[Bumeran] Error en {listing['url'][:60]}: {e}")

                page_num += 1
                await self.human_delay(2, 3)

        await page.close()

    # ─── Detalle ──────────────────────────────────────────────────────────────

    async def get_job_detail(self, url: str) -> JobListing:
        page = await self.new_page()
        try:
            full_url = url if url.startswith("http") else f"{BASE_URL}{url}"
            await self.safe_goto(page, full_url)
            await self.human_delay(1, 2)
            await self.random_scroll(page, 100, 400)

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            # ── Fuente 1: JSON-LD JobPosting ───────────────────────────────────
            job_ld = self._extract_job_ld(soup)
            if job_ld:
                return self._parse_from_json_ld(job_ld, full_url)

            # ── Fuente 2: CSS + meta tags ──────────────────────────────────────
            return self._parse_from_html(soup, full_url)

        finally:
            await page.close()

    # ─── Parsers ──────────────────────────────────────────────────────────────

    def _parse_from_json_ld(self, ld: dict, url: str) -> JobListing:
        title = ld.get("title") or "Sin título"

        hiring_org = ld.get("hiringOrganization") or {}
        company = (
            hiring_org.get("name")
            or (ld.get("employerOverview") or "")[:60]
            or "Empresa no especificada"
        )

        # Ubicación
        location = "Argentina"
        job_loc = ld.get("jobLocation")
        if isinstance(job_loc, list):
            job_loc = job_loc[0] if job_loc else {}
        if isinstance(job_loc, dict):
            addr = job_loc.get("address") or job_loc
            location = (
                addr.get("addressLocality")
                or addr.get("addressRegion")
                or "Argentina"
            )

        # Descripción
        desc_html = ld.get("description", "")
        description = re.sub(r"<[^>]+>", " ", desc_html).strip()
        description = re.sub(r"\s+", " ", description)

        # Modalidad (usa jobLocationType en JSON-LD estándar)
        work_location_type = ld.get("jobLocationType", "")
        employment_type = ld.get("employmentType", "")
        modality = self._detect_modality_from_text(
            work_location_type + " " + employment_type + " " + description
        )

        # Salario
        salary = None
        base_sal = ld.get("baseSalary")
        if isinstance(base_sal, dict):
            val = base_sal.get("value", {})
            if isinstance(val, dict):
                mn = val.get("minValue", "")
                mx = val.get("maxValue", "")
                unit = val.get("unitText", "")
                if mn or mx:
                    salary = f"${mn}-${mx} {unit}".strip()

        # Requisitos
        desc_soup = BeautifulSoup(desc_html, "lxml")
        requirements = [
            li.get_text(strip=True)
            for li in desc_soup.find_all("li")
            if len(li.get_text(strip=True)) > 5
        ]

        return JobListing(
            id=str(uuid.uuid4()),
            portal=Portal.BUMERAN,
            url=url,
            title=title,
            company=company,
            location=location,
            modality=modality,
            salary_range=salary,
            description=description[:5000],
            requirements=requirements[:25],
            posted_at=ld.get("datePosted"),
        )

    def _parse_from_html(self, soup: BeautifulSoup, url: str) -> JobListing:
        """Fallback CSS para cuando no hay JSON-LD."""
        title = (
            self._text(soup.select_one("h1"))
            or self._meta(soup, "og:title")
            or "Sin título"
        )

        # Empresa: Bumeran la pone en varios lugares según versión del layout
        company = (
            self._text(soup.select_one(
                "a[class*='company'], span[class*='company'], "
                "div[class*='employer'] a, p[class*='employer']"
            ))
            or self._meta(soup, "og:site_name")
            or "Empresa no especificada"
        )

        location_el = soup.select_one(
            "span[class*='location'], div[class*='location'], "
            "li[class*='location'], p[class*='location']"
        )
        location = self._text(location_el) or "Argentina"

        salary_el = soup.select_one(
            "span[class*='salary'], div[class*='salary'], "
            "li[class*='salary'], span[class*='sueldo']"
        )
        salary = self._text(salary_el)

        desc_el = soup.select_one(
            "div[class*='description'], section[class*='description'], "
            "div[class*='aviso'], section[class*='aviso']"
        )
        description = (
            desc_el.get_text(separator="\n", strip=True)
            if desc_el
            else self._meta(soup, "og:description") or ""
        )

        requirements = [
            li.get_text(strip=True)
            for li in (desc_el.select("li") if desc_el else [])
            if len(li.get_text(strip=True)) > 5
        ]

        modality = self._detect_modality_from_text(description + " " + title)

        return JobListing(
            id=str(uuid.uuid4()),
            portal=Portal.BUMERAN,
            url=url,
            title=title,
            company=company,
            location=location,
            modality=modality,
            salary_range=salary,
            description=description[:5000],
            requirements=requirements[:25],
        )

    # ─── Parseo de listado ────────────────────────────────────────────────────

    def _parse_listings(self, html: str) -> list[dict]:
        """
        Extrae links de vacantes del listado.
        Bumeran usa URLs del tipo /empleos/<slug>-<id>.html
        """
        soup = BeautifulSoup(html, "lxml")
        seen: set[str] = set()
        results = []

        for a in soup.find_all("a", href=True):
            href: str = a.get("href", "").split("?")[0]

            # Debe contener /empleos/ y terminar en .html, y tener un ID numérico
            if not re.search(r"/empleos/[^/]+-\d{6,}\.html", href):
                continue

            full = href if href.startswith("http") else f"{BASE_URL}{href}"
            if full in seen:
                continue

            # El texto del link debe ser el título (descartamos links sin texto real)
            title = a.get_text(strip=True)
            if len(title) < 8:
                # Intentar extraer del aria-label o title attr
                title = a.get("aria-label") or a.get("title") or title

            seen.add(full)
            results.append({"url": full, "title": title})

        logger.debug(f"[Bumeran] Listings parseados: {len(results)}")
        return results

    # ─── URL builders ─────────────────────────────────────────────────────────

    def _build_search_url(self, keyword: str, page: int = 1) -> str:
        """
        Bumeran usa slugs con guiones.
        Ejemplo: /empleos-busqueda-desarrollador-python.html
        """
        slug = re.sub(r"[^a-z0-9\s]", "", keyword.lower())
        slug = re.sub(r"\s+", "-", slug.strip())
        if page == 1:
            return f"{BASE_URL}/empleos-busqueda-{slug}.html"
        return f"{BASE_URL}/empleos-busqueda-{slug}-pagina-{page}.html"

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _extract_job_ld(self, soup: BeautifulSoup) -> dict:
        """Extrae JSON-LD de tipo JobPosting."""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = script.string or ""
                if not raw.strip():
                    continue
                data = json.loads(raw)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "JobPosting":
                            return item
                if isinstance(data, dict):
                    if data.get("@type") == "JobPosting":
                        return data
                    # Fallback: bloque con campos clave de un JobPosting
                    if "title" in data and "description" in data and "hiringOrganization" in data:
                        return data
            except Exception:
                continue
        return {}

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str | None:
        el = (
            soup.find("meta", attrs={"property": name})
            or soup.find("meta", attrs={"name": name})
        )
        return el.get("content", "").strip() if el else None
