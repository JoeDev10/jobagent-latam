"""
Scraper para ZonaJobs Argentina (zonajobs.com.ar)

Nota: ZonaJobs y Bumeran comparten el mismo grupo (InfoJobs LATAM),
por lo que su estructura HTML y JSON-LD es muy similar.

Estrategia de extracción:
  1. JSON-LD con @type = JobPosting
  2. Meta tags OG
  3. Selectores CSS con fallbacks
"""
import json
import re
import uuid
from typing import AsyncGenerator
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from core import JobListing, JobModality, Portal, SearchConfig, get_logger
from .base import BaseScraper

logger = get_logger(__name__)

BASE_URL = "https://www.zonajobs.com.ar"


class ZonaJobsScraper(BaseScraper):
    portal_name = "zonajobs"

    # ─── Búsqueda ─────────────────────────────────────────────────────────────

    async def search(self, config: SearchConfig) -> AsyncGenerator[JobListing, None]:
        page = await self.new_page()

        for keyword in config.keywords:
            logger.info(f"[ZonaJobs] Buscando: '{keyword}'")
            results_found = 0
            page_num = 1
            prev_urls: set[str] = set()

            while results_found < config.max_results_per_portal:
                search_url = self._build_search_url(keyword, page_num)
                try:
                    await self.safe_goto(page, search_url)
                except Exception as e:
                    logger.error(f"[ZonaJobs] Fallo cargando página {page_num}: {e}")
                    break

                await self.human_delay(2, 4)
                await self.random_scroll(page, 200, 600)

                html = await page.content()
                listings = self._parse_listings(html)

                if not listings:
                    logger.info(f"[ZonaJobs] Sin resultados en página {page_num}")
                    break

                page_urls = {l["url"] for l in listings}
                if page_urls and page_urls == prev_urls:
                    logger.info(f"[ZonaJobs] Página {page_num} repite — fin de resultados")
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
                        logger.warning(f"[ZonaJobs] Error en {listing['url'][:60]}: {e}")

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

            # ── Fuente 1: JSON-LD ──────────────────────────────────────────────
            job_ld = self._extract_job_ld(soup)
            if job_ld:
                return self._parse_from_json_ld(job_ld, full_url, soup)

            # ── Fuente 2: CSS + meta tags ──────────────────────────────────────
            return self._parse_from_html(soup, full_url)

        finally:
            await page.close()

    # ─── Parsers ──────────────────────────────────────────────────────────────

    def _parse_from_json_ld(self, ld: dict, url: str, soup: BeautifulSoup) -> JobListing:
        title = ld.get("title") or "Sin título"

        hiring_org = ld.get("hiringOrganization") or {}
        company = hiring_org.get("name") or "Empresa no especificada"

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

        work_location_type = ld.get("jobLocationType", "")
        employment_type = ld.get("employmentType", "")
        modality = self._detect_modality_from_text(
            work_location_type + " " + employment_type + " " + description
        )

        # Salario (raro, pero por si acaso)
        salary = self._text(soup.select_one(
            "span[class*='salary'], div[class*='salary'], "
            "span[class*='sueldo'], li[class*='salary']"
        ))

        # Requisitos
        desc_soup = BeautifulSoup(desc_html, "lxml")
        requirements = [
            li.get_text(strip=True)
            for li in desc_soup.find_all("li")
            if len(li.get_text(strip=True)) > 5
        ]

        return JobListing(
            id=str(uuid.uuid4()),
            portal=Portal.ZONAJOBS,
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
        """Fallback CSS cuando no hay JSON-LD."""
        title = (
            self._text(soup.select_one("h1, h1[class*='title'], h1[class*='aviso']"))
            or self._meta(soup, "og:title")
            or "Sin título"
        )

        company = (
            self._text(soup.select_one(
                "span.company-name, a[class*='company'], "
                "div[class*='company'] a, p[class*='company']"
            ))
            or self._meta(soup, "og:site_name")
            or "Empresa no especificada"
        )

        location_el = soup.select_one(
            "span[class*='location'], li[class*='location'], "
            "div[class*='location'], p[class*='location']"
        )
        location = self._text(location_el) or "Argentina"

        salary_el = soup.select_one(
            "span[class*='salary'], li[class*='salary'], "
            "span[class*='sueldo'], div[class*='salary']"
        )
        salary = self._text(salary_el)

        desc_el = soup.select_one(
            "div.aviso-description, div[class*='description'], "
            "section[class*='description'], div[class*='aviso-detail']"
        )
        if not desc_el:
            desc_el = soup.select_one("main, article")
        description = (
            desc_el.get_text(separator="\n", strip=True)[:5000]
            if desc_el
            else self._meta(soup, "og:description") or ""
        )

        requirements = [
            li.get_text(strip=True)
            for li in (desc_el.select("li") if desc_el else [])
            if len(li.get_text(strip=True)) > 5
        ]

        modality = self._detect_modality_from_text(description + " " + title)

        posted_el = soup.select_one("time[datetime], span[class*='date']")
        posted_at = None
        if posted_el:
            posted_at = posted_el.get("datetime") or self._text(posted_el)

        return JobListing(
            id=str(uuid.uuid4()),
            portal=Portal.ZONAJOBS,
            url=url,
            title=title,
            company=company,
            location=location,
            modality=modality,
            salary_range=salary,
            description=description,
            requirements=requirements[:25],
            posted_at=posted_at,
        )

    # ─── Parseo de listado ────────────────────────────────────────────────────

    def _parse_listings(self, html: str) -> list[dict]:
        """
        ZonaJobs usa URLs del tipo /empleos/<slug>-<id>
        (sin .html, a diferencia de Bumeran)
        """
        soup = BeautifulSoup(html, "lxml")
        seen: set[str] = set()
        results = []

        for a in soup.find_all("a", href=True):
            href: str = a.get("href", "").split("?")[0]

            # Patrón: /empleos/<texto>-<número>
            if not re.search(r"/empleos/[^/]+-\d{4,}", href):
                continue

            full = href if href.startswith("http") else f"{BASE_URL}{href}"
            if full in seen:
                continue

            title = a.get_text(strip=True)
            if len(title) < 5:
                title = a.get("aria-label") or a.get("title") or title

            seen.add(full)
            results.append({"url": full, "title": title})

        logger.debug(f"[ZonaJobs] Listings parseados: {len(results)}")
        return results

    # ─── URL builders ─────────────────────────────────────────────────────────

    def _build_search_url(self, keyword: str, page: int = 1) -> str:
        q = quote_plus(keyword)
        if page == 1:
            return f"{BASE_URL}/empleos?q={q}&l=Argentina"
        return f"{BASE_URL}/empleos?q={q}&l=Argentina&pg={page}"

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _extract_job_ld(self, soup: BeautifulSoup) -> dict:
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
