"""
Tests del cliente de Mercado Pago (web/payments.py).

No se prueban las llamadas HTTP reales (create_preference/get_payment), sino la
lógica pura y crítica para cobrar bien:
  - parse_webhook_body: MP manda el pago en varios formatos (body JSON, query
    params, resource como URL). Si lo parseamos mal, perdemos pagos.
  - verify_signature: valida la firma HMAC del webhook. Si falla, cualquiera
    podría falsificar un "pago aprobado".
  - is_configured / price_ars: lectura de configuración por env var.
"""
import hashlib
import hmac

from web import payments


class TestIsConfigured:

    def test_sin_token_no_esta_configurado(self, monkeypatch):
        monkeypatch.delenv("MP_ACCESS_TOKEN", raising=False)
        assert payments.is_configured() is False

    def test_con_token_esta_configurado(self, monkeypatch):
        monkeypatch.setenv("MP_ACCESS_TOKEN", "TEST-123")
        assert payments.is_configured() is True


class TestPriceArs:

    def test_default(self, monkeypatch):
        monkeypatch.delenv("MP_PRICE_ARS", raising=False)
        assert payments.price_ars() == 14990.0

    def test_valor_custom(self, monkeypatch):
        monkeypatch.setenv("MP_PRICE_ARS", "9990")
        assert payments.price_ars() == 9990.0

    def test_valor_invalido_cae_al_default(self, monkeypatch):
        monkeypatch.setenv("MP_PRICE_ARS", "no-es-numero")
        assert payments.price_ars() == 14990.0


class TestParseWebhookBody:

    def test_formato_body_json(self):
        topic, rid = payments.parse_webhook_body(
            {"type": "payment", "data": {"id": "999"}}, {}
        )
        assert topic == "payment"
        assert rid == "999"

    def test_formato_query_params(self):
        topic, rid = payments.parse_webhook_body(
            {}, {"topic": ["payment"], "id": ["555"]}
        )
        assert topic == "payment"
        assert rid == "555"

    def test_resource_como_url_extrae_el_id_final(self):
        topic, rid = payments.parse_webhook_body(
            {"topic": "payment", "resource": "https://api.mercadopago.com/v1/payments/777"}, {}
        )
        assert topic == "payment"
        assert rid == "777"

    def test_data_id_en_query(self):
        topic, rid = payments.parse_webhook_body(
            {}, {"type": ["payment"], "data.id": ["888"]}
        )
        assert topic == "payment"
        assert rid == "888"

    def test_sin_datos_devuelve_topic_vacio_y_none(self):
        topic, rid = payments.parse_webhook_body({}, {})
        assert topic == ""
        assert rid is None


class TestVerifySignature:

    def _firma_valida(self, secret: str, rid: str, req_id: str, ts: str) -> str:
        template = f"id:{rid};request-id:{req_id};ts:{ts};"
        h = hmac.new(secret.encode(), template.encode(), hashlib.sha256).hexdigest()
        return f"ts={ts},v1={h}"

    def test_sin_secret_la_validacion_esta_deshabilitada(self, monkeypatch):
        """En dev, sin MP_WEBHOOK_SECRET, se acepta todo (devuelve True)."""
        monkeypatch.delenv("MP_WEBHOOK_SECRET", raising=False)
        assert payments.verify_signature("ts=1,v1=loquesea", "req", "123") is True

    def test_firma_valida_se_acepta(self, monkeypatch):
        monkeypatch.setenv("MP_WEBHOOK_SECRET", "supersecreto")
        xsig = self._firma_valida("supersecreto", "12345", "req-abc", "1700000000")
        assert payments.verify_signature(xsig, "req-abc", "12345") is True

    def test_firma_invalida_se_rechaza(self, monkeypatch):
        monkeypatch.setenv("MP_WEBHOOK_SECRET", "supersecreto")
        assert payments.verify_signature("ts=1700000000,v1=deadbeef", "req-abc", "12345") is False

    def test_firma_de_otro_secret_se_rechaza(self, monkeypatch):
        monkeypatch.setenv("MP_WEBHOOK_SECRET", "supersecreto")
        xsig_atacante = self._firma_valida("secret-equivocado", "12345", "req-abc", "1700000000")
        assert payments.verify_signature(xsig_atacante, "req-abc", "12345") is False

    def test_falta_header_o_resource_se_rechaza(self, monkeypatch):
        monkeypatch.setenv("MP_WEBHOOK_SECRET", "supersecreto")
        assert payments.verify_signature(None, "req", "123") is False
        assert payments.verify_signature("ts=1,v1=abc", "req", None) is False

    def test_header_sin_ts_o_v1_se_rechaza(self, monkeypatch):
        monkeypatch.setenv("MP_WEBHOOK_SECRET", "supersecreto")
        assert payments.verify_signature("v1=abc", "req", "123") is False   # falta ts
        assert payments.verify_signature("ts=1", "req", "123") is False      # falta v1
