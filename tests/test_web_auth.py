"""
Tests de autenticación del SaaS (web/auth.py).

auth.py maneja CONTRASEÑAS y SESIONES, así que es el módulo más sensible:
  - hash_password / verify_password (PBKDF2-HMAC-SHA256 con salt)
  - create_token / verify_token (token firmado con HMAC, tipo JWT casero)

No usa red ni DB: son funciones puras, ideales para testear.
"""
import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta

from web import auth


def _firmar(payload: dict) -> str:
    """Construye un token válido a mano, con la misma lógica que create_token,
    para poder forzar payloads (ej. uno ya expirado)."""
    data = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(auth.SECRET_KEY.encode(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}.{sig}"


class TestPasswordHashing:

    def test_hash_tiene_formato_salt_dolar_hash(self):
        h = auth.hash_password("claveSegura123")
        assert "$" in h
        salt, dk = h.split("$", 1)
        assert len(salt) == 32      # 16 bytes en hex
        assert len(dk) == 64        # sha256 en hex

    def test_misma_clave_genera_hashes_distintos(self):
        """Salt aleatorio → dos hashes de la misma clave NO coinciden (anti rainbow tables)."""
        assert auth.hash_password("misma") != auth.hash_password("misma")

    def test_verify_clave_correcta(self):
        h = auth.hash_password("claveSegura123")
        assert auth.verify_password("claveSegura123", h) is True

    def test_verify_clave_incorrecta(self):
        h = auth.hash_password("claveSegura123")
        assert auth.verify_password("otraClave", h) is False

    def test_verify_no_explota_con_hash_malformado(self):
        assert auth.verify_password("x", "sin-formato-valido") is False
        assert auth.verify_password("x", "") is False


class TestTokens:

    def test_round_trip_devuelve_sub_y_email(self):
        token = auth.create_token(42, "joel@example.com")
        payload = auth.verify_token(token)
        assert payload is not None
        assert payload["sub"] == 42
        assert payload["email"] == "joel@example.com"

    def test_token_con_firma_adulterada_es_rechazado(self):
        token = auth.create_token(1, "a@b.com")
        data, _sig = token.rsplit(".", 1)
        adulterado = f"{data}.firmafalsa00000000"
        assert auth.verify_token(adulterado) is None

    def test_token_con_payload_modificado_es_rechazado(self):
        """Cambiar el payload sin re-firmar invalida la firma."""
        token = auth.create_token(1, "a@b.com")
        _data, sig = token.rsplit(".", 1)
        otro_payload = base64.urlsafe_b64encode(
            json.dumps({"sub": 999, "email": "hacker@x.com", "exp": "2099-01-01T00:00:00"}).encode()
        ).decode().rstrip("=")
        assert auth.verify_token(f"{otro_payload}.{sig}") is None

    def test_token_expirado_es_rechazado(self):
        vencido = _firmar({
            "sub": 1,
            "email": "a@b.com",
            "exp": (datetime.utcnow() - timedelta(days=1)).isoformat(),
        })
        assert auth.verify_token(vencido) is None

    def test_token_vigente_se_acepta(self):
        exp = (datetime.utcnow() + timedelta(days=1)).isoformat()
        vigente = _firmar({"sub": 7, "email": "a@b.com", "exp": exp})
        payload = auth.verify_token(vigente)
        assert payload is not None
        assert payload["sub"] == 7
        assert payload["exp"] == exp

    def test_token_basura_devuelve_none(self):
        assert auth.verify_token("no-es-un-token") is None
        assert auth.verify_token("") is None
