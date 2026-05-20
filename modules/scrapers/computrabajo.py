"""
Scraper para Computrabajo Argentina (ar.computrabajo.com)

Estrategia de extracción (en orden de preferencia):
  1. JSON-LD <script type="application/ld+json"> con @type = JobPosting
  2. Meta tags (og:title, og:description)
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

BASE_URL = "https://ar.computrabajo.com"


class ComputrabajoScraper(BaseScraper):
    portal_name = "computrabajo"

    # ─── Búsqueda ─────────────────────────────────────────────────────────────

    async def search(self, config: SearchConfig) -> AsyncGenerator[JobListing, None]:
        page = await self.new_page()

        for keyword in config.keywords:
            logger.info(f"[Computrabajo] Buscando: '{keyword}' en {config.location}")
            results_found = 0

            search_url = self._build_search_url(keyword, config.location)
            try:
                await self.safe_goto(page, search_url)
            except Exception as e:
                logger.error(f"[Computrabajo] No se pudo cargar búsqueda de '{keyword}': {e}")
                continue

            await self.human_delay(1.5, 3)
            await self.random_scroll(page, 200, 500)

            page_num = 1
            while results_found < config.max_results_per_portal:
                html = await page.content()
                listings = self._parse_listings(html)

                if not listings:
                    logger.info(f"[Computrabajo] Sin resultados en página {page_num}")
                    break

                for listing in listings:
                    if results_found >= config.max_results_per_portal:
                        break
                    try:
                        detail = await self.get_job_detail(listing["url"])
                        results_found += 1
                        yield detail
                        await self.human_delay(1, 3)
                    except Exception as e:
                        logger.warning(f"[Computrabajo] Error en {listing['url'][:60]}: {e}")
                        continue

                # Paginación
                next_url = self._next_page_url(search_url, page_num + 1)
                if not next_url or page_num >= 10:
                    break

                try:
                    await self.safe_goto(page, next_url)
                    await self.human_delay(2, 4)
                    await self.random_scroll(page)
                    page_num += 1
                except Exception:
                    break

        await page.close()

    # ─── Detalle ──────────────────────────────────────────────────────────────

    async def get_job_detail(self, url: str) -> JobListing:
        page = await self.new_page()
        try:
            full_url = url if url.startswith("http") else f"{BASE_URL}{url}"
            await self.safe_goto(page, full_url)
            await self.human_delay(1, 2)
            await self.random_scroll(page, 100, 400)
            await self.random_mouse_move(page)

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            # ── Fuente 1: JSON-LD ──────────────────────────────────────────────
            job_ld = self._extract_json_ld(soup)
            if job_ld:
                return self._parse_from_json_ld(job_ld, full_url)

            # ── Fuente 2: Meta tags + CSS ──────────────────────────────────────
            return self._parse_from_html(soup, full_url)

        finally:
            await page.close()

    # ─── Parsers ──────────────────────────────────────────────────────────────

    def _parse_from_json_ld(self, ld: dict, url: str) -> JobListing:
        """Construye JobListing a partir de datos JSON-LD."""
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

        # Descripción (viene como HTML)
        desc_html = ld.get("description", "")
        description = re.sub(r"<[^>]+>", " ", desc_html).strip()
        description = re.sub(r"\s+", " ", description)

        # Modalidad
        work_location = ld.get("jobLocationType", "")
        modality = self._detect_modality_from_text(work_location + " " + description)

        # Salario
        salary = None
        base_sal = ld.get("baseSalary")
        if isinstance(base_sal, dict):
            val = base_sal.get("value", {})
            if isinstance(val, dict):
                mn = val.get("minValue", "")
                mx = val.get("maxValue", "")
                currency = val.get("currency", "ARS")
                if mn or mx:
                    salary = f"{mn}-{mx} {currency}".strip("- ")

        # Requisitos
        desc_soup = BeautifulSoup(desc_html, "lxml")
        requirements = [
            li.get_text(strip=True)
            for li in desc_soup.find_all("li")
            if len(li.get_text(strip=True)) > 5
        ]

        return JobListing(
            id=str(uuid.uuid4()),
            portal=Portal.COMPUTRABAJO,
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
        """Fallback: construye JobListing desde CSS/meta tags."""
        # Título
        title = (
            self._text(soup.select_one("h1"))
            or self._meta(soup, "og:title")
            or "Sin título"
        )

        # Empresa
        company = (
            self._text(soup.select_one(
                "a[data-ga*='company'], span[class*='company'], "
                "p.fs16 a, div.company a, .company-name"
            ))
            or self._meta(soup, "og:site_name")
            or "Empresa no especificada"
        )

        # Ubicación
        location_el = soup.select_one(
            "span[class*='location'], p.location, div.location, "
            "span[itemprop='addressLocality'], span.fs13.fc_base"
        )
        location = self._text(location_el) or "Argentina"

        # Salario
        salary_el = soup.select_one(
            "span[class*='salary'], span[class*='sueldo'], "
            "div[class*='salary'], p[class*='salary']"
        )
        salary = self._text(salary_el)

        # Descripción
        description = ""
        for sel in [
            "div.box_detail section", "div[class*='description']",
            "section[class*='description']", "article.box_offer_detail",
            "div#jobDescriptionText", "div.box_detail",
        ]:
            el = soup.select_one(sel)
            if el:
                description = el.get_text(separator="\n", strip=True)[:5000]
                break

        if not description:
            meta_desc = self._meta(soup, "og:description") or self._meta(soup, "description")
            description = meta_desc or ""

        # Requisitos
        requirements = [
            li.get_text(strip=True)
            for li in soup.select("div.box_detail li, article li")
            if len(li.get_text(strip=True)) > 5
        ]

        modality = self._detect_modality_from_text(description + " " + title)

        # Fecha
        posted_el = soup.select_one("time[datetime], span[class*='date'], p.fc_aux.fs13")
        posted_at = None
        if posted_el:
            posted_at = posted_el.get("datetime") or self._text(posted_el)

        return JobListing(
            id=str(uuid.uuid4()),
            portal=Portal.COMPUTRABAJO,
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
        soup = BeautifulSoup(html, "lxml")
        results = []
        seen: set[str] = set()

        # Selectores en orden de preferencia (CT cambia clases con frecuencia)
        selectors = [
            # Selector moderno 2024-2025
            "article[data-id] h2 a",
            "article.box_offer h2 a",
            "div[class*='offer'] h2 a",
            # Selector alternativo
            "a.js-o-link[href*='/trabajo-de-']",
            "a.js-o-link[href*='/empleo-']",
            # Genérico: links con slug de trabajo
            "a[href*='/trabajo-de-'][href*='.html']",
            "a[href*='/empleo-'][href*='.html']",
        ]

        for sel in selectors:
            for el in soup.select(sel):
                href = el.get("href", "").split("?")[0].split("#")[0]
                if not href:
                    continue
                full = href if href.startswith("http") else f"{BASE_URL}{href}"
                if full in seen:
                    continue
                title = el.get_text(strip=True)
                if len(title) < 4:
                    continue
                seen.add(full)
                results.append({"url": full, "title": title})

            if results:
                break  # usamos el primer selector que devuelva resultados

        logger.debug(f"[Computrabajo] Listings parseados: {len(results)}")
        return results

    # ─── URL builders ─────────────────────────────────────────────────────────

    def _build_search_url(self, keyword: str, location: str) -> str:
        """
        Computrabajo usa slugs con guiones.
        Ejemplo: /trabajo-de-desarrollador-python
        """
        kw_slug = re.sub(r"[^a-z0-9\s]", "", keyword.lower())
        kw_slug = re.sub(r"\s+", "-", kw_slug.strip())

        loc_map = {
            "argentina": "",
            "buenos aires": "/buenos-aires",
            "caba": "/buenos-aires",
            "córdoba": "/cordoba",
            "cordoba": "/cordoba",
            "rosario": "/rosario",
            "mendoza": "/mendoza",
            "tucuman": "/tucuman",
            "tucumán": "/tucuman",
        }
        loc_slug = loc_map.get(location.lower(), "")
        return f"{BASE_URL}/trabajo-de-{kw_slug}{loc_slug}"

    def _next_page_url(self, base_search_url: str, page_num: int) -> str | None:
        """Construye la URL de la siguiente página de resultados."""
        if page_num < 2:
            return None
        # CT usa ?p=2 o &p=2 como paginación
        if "?" in base_search_url:
            return f"{base_search_url}&p={page_num}"
        return f"{base_search_url}?p={page_num}"

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _extract_json_ld(self, soup: BeautifulSoup) -> dict:
        """
        Extrae el primer bloque JSON-LD con @type = JobPosting.
        Fallback: cualquier bloque con title + description.
        """
        job_ld = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = script.string or ""
                if not raw.strip():
                    continue
                data = json.loads(raw)
                # Lista de objetos
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "JobPosting":
                            return item
                # Objeto único
                if isinstance(data, dict):
                    if data.get("@type") == "JobPosting":
                        return data
                    # Fallback menos específico
                    if "title" in data and "description" in data and not job_ld:
                        job_ld = data
            except Exception:
                continue
        return job_ld

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str | None:
        """Lee un meta tag por property o name."""
        el = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        return el.get("content", "").strip() if el else None
