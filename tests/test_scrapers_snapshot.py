"""
Snapshot tests de scrapers (Roadmap v0.2).

Idea: en vez de pegarle al sitio real (lento, frágil, depende de la red y de
no estar logueado), guardamos un HTML FIJO que imita la estructura del listado
de cada portal y verificamos que `_parse_listings` extrae las vacantes bien.

Esto detecta el problema #1 de cualquier scraper: que el portal cambie sus
clases/selectores CSS y el parser empiece a devolver 0 resultados sin avisar.

`_parse_listings(html) -> list[dict]` es una función pura (no usa red ni
Playwright), así que se puede testear instanciando el scraper directamente:
`BaseScraper.__init__` no abre ningún navegador, solo setea atributos.
"""
import re

import pytest

from modules.scrapers.computrabajo import ComputrabajoScraper, BASE_URL as CT_BASE
from modules.scrapers.bumeran import BumeranScraper, BASE_URL as BM_BASE


# ─── Computrabajo ──────────────────────────────────────────────────────────────

# HTML fijado: estructura del selector moderno `article[data-id] h2 a`.
# Incluye a propósito: una URL con query string, una relativa, una absoluta,
# un duplicado y un título demasiado corto (deben filtrarse).
COMPUTRABAJO_HTML = """
<html><body>
  <div class="results">
    <article data-id="101">
      <h2><a href="/trabajo-de-desarrollador-python/abc101.html?utm=feed">Desarrollador Python Semi Senior</a></h2>
    </article>
    <article data-id="102">
      <h2><a href="/trabajo-de-qa-tester/abc102.html">QA Tester</a></h2>
    </article>
    <article data-id="103">
      <h2><a href="https://ar.computrabajo.com/trabajo-de-analista-datos/abc103.html">Analista de Datos</a></h2>
    </article>
    <!-- Duplicado: misma URL que el 102 -->
    <article data-id="104">
      <h2><a href="/trabajo-de-qa-tester/abc102.html">QA Tester (repetido)</a></h2>
    </article>
    <!-- Titulo demasiado corto (&lt; 4 chars): se descarta -->
    <article data-id="105">
      <h2><a href="/trabajo-de-x/abc105.html">QA</a></h2>
    </article>
  </div>
</body></html>
"""


class TestComputrabajoListings:

    @pytest.fixture
    def listings(self):
        return ComputrabajoScraper()._parse_listings(COMPUTRABAJO_HTML)

    def test_extrae_las_vacantes_validas(self, listings):
        """3 vacantes únicas y válidas (el duplicado y el título corto se filtran)."""
        assert len(listings) == 3

    def test_no_hay_urls_duplicadas(self, listings):
        urls = [l["url"] for l in listings]
        assert len(urls) == len(set(urls))

    def test_url_relativa_se_vuelve_absoluta(self, listings):
        urls = [l["url"] for l in listings]
        assert f"{CT_BASE}/trabajo-de-desarrollador-python/abc101.html" in urls

    def test_query_string_se_elimina(self, listings):
        assert all("?" not in l["url"] for l in listings)

    def test_titulos_correctos(self, listings):
        titulos = {l["title"] for l in listings}
        assert "Desarrollador Python Semi Senior" in titulos
        assert "Analista de Datos" in titulos

    def test_titulo_corto_se_descarta(self, listings):
        assert all(l["title"] != "QA" for l in listings)

    def test_selectores_rotos_devuelven_lista_vacia_sin_crashear(self):
        """Si el portal cambia TODA su estructura, no debe explotar: lista vacía."""
        html_sin_estructura = "<html><body><div>Sin vacantes acá</div></body></html>"
        assert ComputrabajoScraper()._parse_listings(html_sin_estructura) == []

    def test_fallback_a_selector_alternativo(self):
        """Si no hay article[data-id], usa el fallback a.js-o-link."""
        html = (
            '<html><body>'
            '<a class="js-o-link" href="/trabajo-de-soporte-tecnico/zzz999.html">Soporte Tecnico</a>'
            '</body></html>'
        )
        listings = ComputrabajoScraper()._parse_listings(html)
        assert len(listings) == 1
        assert listings[0]["title"] == "Soporte Tecnico"


# ─── Bumeran ─────────────────────────────────────────────────────────────────

# Bumeran identifica vacantes por URLs tipo /empleos/<slug>-<id6+>.html
BUMERAN_HTML = """
<html><body>
  <ul>
    <li><a href="/empleos/desarrollador-python-ssr-1234567.html?ref=list">Desarrollador Python SSR</a></li>
    <li><a href="/empleos/qa-automation-engineer-7654321.html">QA Automation Engineer</a></li>
    <li><a href="https://www.bumeran.com.ar/empleos/analista-funcional-9988776.html">Analista Funcional</a></li>
    <!-- Duplicado de la 2da -->
    <li><a href="/empleos/qa-automation-engineer-7654321.html">QA dup</a></li>
    <!-- No es vacante: link a empresa -->
    <li><a href="/empresas/acme-corp.html">Acme Corp</a></li>
    <!-- No es vacante: ID muy corto (menos de 6 digitos) -->
    <li><a href="/empleos/cadete-123.html">Cadete</a></li>
    <!-- Titulo corto: debe caer al aria-label -->
    <li><a href="/empleos/dev-555444.html" aria-label="Desarrollador Backend">Dev</a></li>
  </ul>
</body></html>
"""

BUMERAN_JOB_RE = re.compile(r"/empleos/[^/]+-\d{6,}\.html$")


class TestBumeranListings:

    @pytest.fixture
    def listings(self):
        return BumeranScraper()._parse_listings(BUMERAN_HTML)

    def test_extrae_las_vacantes_validas(self, listings):
        """4 únicas: el duplicado, el link de empresa y el ID corto se filtran."""
        assert len(listings) == 4

    def test_solo_urls_de_vacante(self, listings):
        for l in listings:
            assert BUMERAN_JOB_RE.search(l["url"]), f"URL no es de vacante: {l['url']}"

    def test_no_hay_urls_duplicadas(self, listings):
        urls = [l["url"] for l in listings]
        assert len(urls) == len(set(urls))

    def test_descarta_links_que_no_son_vacantes(self, listings):
        urls = " ".join(l["url"] for l in listings)
        assert "/empresas/" not in urls          # link de empresa
        assert "cadete-123" not in urls           # ID de menos de 6 dígitos

    def test_url_relativa_se_vuelve_absoluta(self, listings):
        urls = [l["url"] for l in listings]
        assert f"{BM_BASE}/empleos/desarrollador-python-ssr-1234567.html" in urls

    def test_query_string_se_elimina(self, listings):
        assert all("?" not in l["url"] for l in listings)

    def test_titulo_corto_cae_al_aria_label(self, listings):
        dev = next(l for l in listings if "dev-555444" in l["url"])
        assert dev["title"] == "Desarrollador Backend"

    def test_selectores_rotos_devuelven_lista_vacia_sin_crashear(self):
        html_sin_estructura = "<html><body><a href='/algo/sin-id.html'>x</a></body></html>"
        assert BumeranScraper()._parse_listings(html_sin_estructura) == []
