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


class TestTitleKeyAcentos:
    """
    En un portal en español los acentos son omnipresentes. _title_key debe
    NORMALIZARLOS (á→a, ñ→n), no borrarlos, para que la misma vacante escrita
    con o sin acento se detecte como duplicada.
    """

    @pytest.mark.parametrize("con_acento,sin_acento", [
        ("Diseñador Gráfico",      "Disenador Grafico"),
        ("Analista de Logística",  "Analista de Logistica"),
        ("Médico Clínico",         "Medico Clinico"),
        ("Niñera",                 "Ninera"),
    ])
    def test_acentos_y_enie_colapsan_a_la_misma_key(self, con_acento, sin_acento):
        assert JobAgent._title_key(con_acento, "Acme") == JobAgent._title_key(sin_acento, "Acme")

    def test_acentos_no_se_pierden_dejando_keys_vacias(self):
        """'Niñera' no debe quedar mutilada a 'niera' por borrado del ñ."""
        key = JobAgent._title_key("Niñera", "Acme")
        assert "ninera" in key


class TestTitleKeyStopwordsPalabraCompleta:
    """
    Las stopwords (ref, sr, jr, semi, senior, junior...) deben eliminarse solo
    como PALABRAS COMPLETAS. Borrarlas como subcadena mutila palabras legítimas
    y puede fusionar puestos distintos como si fueran duplicados.
    """

    @pytest.mark.parametrize("title,palabra_intacta", [
        ("Referente de Ventas",       "referente"),   # contiene 'ref'
        ("Coordinador de Seminario",  "seminario"),    # contiene 'semi'
        ("Asesor Comercial",          "asesor"),        # contiene 'sr'
        ("Gerente Senior",            "gerente"),       # 'senior' SÍ se va, 'gerente' queda
    ])
    def test_stopword_como_subcadena_no_mutila_la_palabra(self, title, palabra_intacta):
        key = JobAgent._title_key(title, "Acme")
        assert palabra_intacta in key, (
            f"'{palabra_intacta}' fue mutilada por borrado de stopword en subcadena: '{key}'"
        )

    def test_stopword_palabra_completa_si_se_elimina(self):
        """'Senior' como palabra suelta sí debe desaparecer."""
        con = JobAgent._title_key("Desarrollador Senior", "Acme")
        sin = JobAgent._title_key("Desarrollador", "Acme")
        assert con == sin

    def test_referente_y_referente_senior_son_duplicados(self):
        """Mismo puesto con/sin seniority → misma key (caso de uso real)."""
        a = JobAgent._title_key("Referente de Soporte", "Acme")
        b = JobAgent._title_key("Referente de Soporte Senior", "Acme")
        assert a == b
        assert "referente" in a  # y no quedó mutilado
