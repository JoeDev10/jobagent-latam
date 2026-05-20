"""
Scraper para Indeed Argentina (ar.indeed.com)

Indeed tiene protección anti-bot agresiva. Estrategias usadas:
  - Stealth fingerprinting (heredado de BaseScraper)
  - Esperas variables entre requests
  - Detección de captcha / bloqueo → skip graceful
  - JSON-LD como fuente primaria en páginas de detalle
  - Múltiples selectores CSS con fallback

Nota: Indeed no permite aplicar directamente (redirige a la empresa).
Las vacantes de Indeed se marcan como PENDING para revisión manual.
"""
import json
import re
import uuid
from typing import AsyncGenerator
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from core import JobListing, JobModality, Portal, SearchConfig, get_logger
from .base import BaseScraper

logger = get_logger(__name__)

BASE_URL = "https://ar.indeed.com"


class IndeedScraper(BaseScraper):
    portal_name = "indeed"

    # ─── Búsqueda ─────────────────────────────────────────────────────────────

    async def search(self, config: SearchConfig) -> AsyncGenerator[JobListing, None]:
        page = await self.new_page()

        for keyword in config.keywords:
            logger.info(f"[Indeed] Buscando: '{keyword}' en {config.location}")
            results_found = 0
            start = 0

            while results_found < config.max_results_per_portal:
                search_url = self._build_search_url(keyword, config.location, start)
                try:
                    await self.safe_goto(page, search_url, retries=2)
                except Exception as e:
                    logger.error(f"[Indeed] Fallo cargando búsqueda (start={start}): {e}")
                    break

                await self.human_delay(2, 4)
                await self.random_scroll(page, 200, 700)
                await self.random_mouse_move(page)

                # Detectar bloqueo / captcha
                if await self._is_blocked(page):
                    logger.warning("[Indeed] Detectado bloqueo o captcha — deteniendo búsqueda")
                    break

                html = await page.content()
                listings = self._parse_listings(html)

                if not listings:
                    logger.info(f"[Indeed] Sin resultados (start={start})")
                    break

                for listing in listings:
                    if results_found >= config.max_results_per_portal:
                        break
                    try:
                        detail = await self.get_job_detail(listing["url"])
                        results_found += 1
                        yield detail
                        await self.human_delay(1.5, 4)
                    except Exception as e:
                        logger.warning(f"[Indeed] Error en {listing['url'][:60]}: {e}")

                start += 10
                await self.human_delay(2, 4)

        await page.close()

    # ─── Detalle ──────────────────────────────────────────────────────────────

    async def get_job_detail(self, url: str) -> JobListing:
        page = await self.new_page()
        try:
            await self.safe_goto(page, url, retries=2)
            await self.human_delay(1.5, 3)
            await self.random_scroll(page, 100, 500)

            if await self._is_blocked(page):
                raise RuntimeError("Indeed bloqueó el acceso a esta página")

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            # ── Fuente 1: JSON-LD ──────────────────────────────────────────────
            job_ld = self._extract_job_ld(soup)
            if job_ld:
                return self._parse_from_json_ld(job_ld, url)

            # ── Fuente 2: CSS (selectores 2024-2025) ──────────────────────────
            return self._parse_from_html(soup, url)

        finally:
            await page.close()

    # ─── Parsers ──────────────────────────────────────────────────────────────

    def _parse_from_json_ld(self, ld: dict, url: str) -> JobListing:
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

        work_loc_type = ld.get("jobLocationType", "")
        employment_type = ld.get("employmentType", "")
        modality = self._detect_modality_from_text(
            work_loc_type + " " + employment_type + " " + description
        )

        # Salario
        salary = None
        base_sal = ld.get("baseSalary") or ld.get("estimatedSalary")
        if isinstance(base_sal, dict):
            val = base_sal.get("value", {})
            if isinstance(val, dict):
                mn = val.get("minValue", "")
                mx = val.get("maxValue", "")
                unit = val.get("unitText", "MONTH")
                if mn or mx:
                    salary = f"${mn}-${mx}/{unit}".replace("$-$", "")

        desc_soup = BeautifulSoup(desc_html, "lxml")
        requirements = [
            li.get_text(strip=True)
            for li in desc_soup.find_all("li")
            if len(li.get_text(strip=True)) > 5
        ]

        return JobListing(
            id=str(uuid.uuid4()),
            portal=Portal.INDEED,
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
        """
        Selectores CSS actualizados para Indeed Argentina 2024-2025.
        Indeed cambia sus clases generadas frecuentemente; usamos data-testid
        y aria attrs que son más estables.
        """
        # Título
        title = (
            self._text(soup.select_one(
                "h1[data-testid='jobsearch-JobInfoHeader-title'], "
                "h1.jobsearch-JobInfoHeader-title, "
                "h1[class*='jobTitle'], h1"
            ))
            or self._meta(soup, "og:title")
            or "Sin título"
        )

        # Empresa
        company = (
            self._text(soup.select_one(
                "div[data-testid='inlineHeader-companyName'] a, "
                "span[data-testid='inlineHeader-companyName'], "
                "div[data-company-name] a, "
                "span.companyName, a[data-testid='employer-name']"
            ))
            or "Empresa no especificada"
        )

        # Ubicación
        location = (
            self._text(soup.select_one(
                "div[data-testid='job-location'], "
                "div[data-testid='inlineHeader-companyLocation'], "
                "div.companyLocation, span[data-testid='job-location']"
            ))
            or "Argentina"
        )

        # Salario
        salary = (
            self._text(soup.select_one(
                "span[data-testid='attribute_snippet_testid'], "
                "div#salaryInfoAndJobType span, "
                "span[class*='salary'], div[class*='salary']"
            ))
        )

        # Descripción
        desc_el = soup.select_one(
            "div#jobDescriptionText, "
            "div.jobsearch-jobDescriptionText, "
            "div[data-testid='jobsearch-JobComponent-description'], "
            "section[id*='description'], div[class*='description']"
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
            portal=Portal.INDEED,
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
        Indeed renderiza las cards con varios patrones según la versión del test A/B.
        Usamos múltiples selectores en cascada.
        """
        soup = BeautifulSoup(html, "lxml")
        results = []
        seen: set[str] = set()

        # Selector 1: cards con data-jk (job key) en el link — más estable
        for card in soup.select("div.job_seen_beacon, li.css-5lfssm, div[data-testid='slider_item']"):
            link = card.select_one("a[data-jk], h2 a[id*='job_'], h2 a")
            if not link:
                continue
            href = link.get("href", "")
            if not href:
                continue
            full = href if href.startswith("http") else f"{BASE_URL}{href}"
            full = full.split("?")[0]
            if full in seen:
                continue
            title = (
                link.get_text(strip=True)
                or link.get("aria-label", "")
                or self._text(card.select_one("h2, h3"))
                or "Sin título"
            )
            seen.add(full)
            results.append({"url": full, "title": title})

        # Selector 2: fallback — cualquier link con /rc/clk o /pagead/clk o /viewjob
        if not results:
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                if not any(p in href for p in ("/rc/clk", "/pagead/clk", "/viewjob", "/clk")):
                    continue
                full = href if href.startswith("http") else f"{BASE_URL}{href}"
                full = full.split("?")[0]
                if full in seen or len(full) < 30:
                    continue
                title = a.get_text(strip=True) or a.get("aria-label", "")
                if len(title) < 5:
                    continue
                seen.add(full)
                results.append({"url": full, "title": title})

        logger.debug(f"[Indeed] Listings parseados: {len(results)}")
        return results

    # ─── URL builders ─────────────────────────────────────────────────────────

    def _build_search_url(self, keyword: str, location: str, start: int = 0) -> str:
        q = quote_plus(keyword)
        l = quote_plus(location)
        url = f"{BASE_URL}/jobs?q={q}&l={l}&sort=date"
        if start > 0:
            url += f"&start={start}"
        return url

    # ─── Anti-bloqueo ─────────────────────────────────────────────────────────

    async def _is_blocked(self, page) -> bool:
        """Detecta si Indeed nos bloqueó o puso un captcha."""
        try:
            title = await page.title()
            url = page.url
            blocked_signals = [
                "captcha", "robot", "blocked", "access denied",
                "security check", "unusual traffic", "403",
            ]
            t = (title + " " + url).lower()
            return any(s in t for s in blocked_signals)
        except Exception:
            return False

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
