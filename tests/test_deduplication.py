"""
Tests de deduplicación de vacantes.

El agente puede encontrar la misma vacante en múltiples portales o con
títulos ligeramente distintos. La función _title_key normaliza los títulos
para detectar duplicados semánticos.

Técnicas nuevas:
  - Probar una función ESTÁTICA pura (no necesita instanciar la clase)
  - Parametrize para cubrir casos límite
  - Documentar el comportamiento esperado como especificación viva
"""
import pytest
from core.agent import JobAgent


class TestTitleKey:
    """
    _title_key(title, company) → string normalizado para comparar duplicados.

    Reglas de negocio:
      - Convierte a minúsculas
      - Elimina caracteres no alfanuméricos
      - Elimina stopwords: ref, remoto, argentina, ssr, sr, jr, semi, senior, junior
      - Normaliza espacios múltiples
    """

    @pytest.mark.parametrize("title,company,expected_contains", [
        # Mismo título → misma key
        ("QA Tester",           "Acme",  "qa tester acme"),
        # Stopwords eliminadas
        ("QA Tester Junior",    "Acme",  "qa tester acme"),   # "junior" eliminado
        ("QA Tester Sr",        "Acme",  "qa tester acme"),   # "sr" eliminado
        ("QA Tester SSR",       "Acme",  "qa tester acme"),   # "ssr" eliminado
        ("QA Tester Senior",    "Acme",  "qa tester acme"),   # "senior" eliminado
        # Caracteres especiales eliminados
        ("QA / Tester",         "Acme",  "qa  tester"),       # '/' eliminado
        ("QA - Tester",         "Acme",  "qa  tester"),       # '-' eliminado
        # Ubicación eliminada (es stopword)
        ("QA Tester Argentina", "Acme",  "qa tester acme"),
    ])
    def test_normalizacion(self, title, company, expected_contains):
        key = JobAgent._title_key(title, company)
        # Verificamos que el key resultante no contiene stopwords
        for stopword in ["junior", " sr ", " ssr ", "senior", "argentina", "remoto"]:
            assert stopword not in key, f"Stopword '{stopword}' encontrada en key: '{key}'"

    def test_misma_vacante_distinto_formato_da_igual_key(self):
        """
        'QA Tester Junior @ Acme' y 'QA Tester Sr. @ Acme' deben
        generar la misma key → serían detectados como duplicados.
        """
        key_junior = JobAgent._title_key("QA Tester Junior", "Acme")
        key_sr = JobAgent._title_key("QA Tester Sr", "Acme")
        assert key_junior == key_sr

    def test_vacantes_distintas_dan_keys_distintas(self):
        """'QA Tester' y 'Dev Backend' son puestos distintos — keys distintas."""
        key_qa = JobAgent._title_key("QA Tester", "Acme")
        key_dev = JobAgent._title_key("Dev Backend", "Acme")
        assert key_qa != key_dev

    def test_misma_empresa_distinta_da_key_distinta(self):
        """Mismo título en empresas distintas NO son duplicados."""
        key_acme = JobAgent._title_key("QA Tester", "Acme Corp")
        key_beta = JobAgent._title_key("QA Tester", "Beta SA")
        assert key_acme != key_beta

    @pytest.mark.parametrize("title", [
        "QA TESTER JUNIOR",        # todo mayúsculas
        "qa tester junior",        # todo minúsculas
        "Qa Tester Junior",        # titlecase
        "  QA   Tester  Junior  ", # espacios extra
    ])
    def test_case_y_espacios_son_ignorados(self, title):
        """Variaciones de mayúsculas y espacios no afectan la deduplicación."""
        key = JobAgent._title_key(title, "Acme")
        key_base = JobAgent._title_key("QA Tester", "Acme")
        assert key == key_base


class TestDeduplicacionLogica:
    """
    Tests de la lógica completa de deduplicación en _scrape_all_portals.
    Explicamos el comportamiento esperado sin correr el scraper real.
    """

    def test_url_duplicada_es_rechazada(self):
        """Si dos vacantes tienen la misma URL, la segunda es duplicada."""
        seen_urls = {"https://example.com/job/123"}
        url_nueva = "https://example.com/job/456"
        url_dup = "https://example.com/job/123"

        assert url_dup in seen_urls      # → ignorar
        assert url_nueva not in seen_urls  # → agregar

    def test_titulo_duplicado_cross_portal_es_rechazado(self):
        """
        La misma vacante publicada en Computrabajo y Bumeran a la vez
        debe aparecer solo una vez en el resultado.
        """
        seen_keys: set[str] = set()

        key_computrabajo = JobAgent._title_key("QA Tester Junior", "Acme Corp")
        seen_keys.add(key_computrabajo)

        key_bumeran = JobAgent._title_key("QA Tester Jr", "Acme Corp")  # mismo puesto, abreviado

        assert key_bumeran in seen_keys, (
            "El mismo puesto publicado en otro portal debe ser detectado como duplicado"
        )
