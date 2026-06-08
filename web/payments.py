"""
Cliente de Mercado Pago (API REST, sin SDK).

Documentación: https://www.mercadopago.com.ar/developers/es/reference

Variables de entorno:
  MP_ACCESS_TOKEN     — Access token (Producción o TEST-...) de la app en mercadopago.com.ar
  MP_WEBHOOK_SECRET   — Secret para validar la firma del webhook (panel MP → Webhooks)
  BASE_URL            — URL pública de la app (ej. https://jobagent-latam.onrender.com)
  MP_PRICE_ARS        — Precio mensual en ARS (default 14990)
  MP_PRICE_USD        — Precio referencia USD (default 15) — solo para mostrar
"""
import hashlib
import hmac
import os
from urllib.parse import urlparse, parse_qs

import httpx

API_BASE = "https://api.mercadopago.com"
DEFAULT_TIMEOUT = 15.0


def is_configured() -> bool:
    return bool(os.environ.get("MP_ACCESS_TOKEN"))


def price_ars() -> float:
    try:
        return float(os.environ.get("MP_PRICE_ARS", "14990"))
    except ValueError:
        return 14990.0


def _base_url() -> str:
    return (os.environ.get("BASE_URL") or "").rstrip("/")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['MP_ACCESS_TOKEN']}",
        "Content-Type": "application/json",
    }


async def create_preference(user_id: int, user_email: str, full_name: str = "") -> dict:
    """
    Crea una preferencia de pago para el plan Pro mensual.
    Devuelve el dict con `id`, `init_point`, `sandbox_init_point`.
    """
    base = _base_url()
    if not base:
        raise RuntimeError("BASE_URL no configurada — Mercado Pago necesita URL pública para webhooks")

    external_reference = f"user_{user_id}"

    body = {
        "items": [
            {
                "title": "VacantIA Pro — Suscripción mensual",
                "description": "Búsquedas ilimitadas de vacantes con IA",
                "quantity": 1,
                "unit_price": price_ars(),
                "currency_id": "ARS",
            }
        ],
        "payer": {
            "email": user_email,
            "name": full_name or user_email.split("@")[0],
        },
        "external_reference": external_reference,
        "back_urls": {
            "success": f"{base}/app/upgrade/success",
            "pending": f"{base}/app/upgrade/pending",
            "failure": f"{base}/app/upgrade/failure",
        },
        "auto_return": "approved",
        "notification_url": f"{base}/api/mp/webhook",
        "statement_descriptor": "VACANTIA",
        "metadata": {"user_id": user_id, "plan": "pro"},
    }

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        r = await client.post(f"{API_BASE}/checkout/preferences", headers=_headers(), json=body)
        r.raise_for_status()
        return r.json()


async def get_payment(payment_id: str) -> dict:
    """Recupera el detalle de un pago desde la API de MP."""
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        r = await client.get(f"{API_BASE}/v1/payments/{payment_id}", headers=_headers())
        r.raise_for_status()
        return r.json()


def parse_webhook_body(body: dict, query_params: dict) -> tuple[str, str | None]:
    """
    Extrae (topic, resource_id) de un webhook de Mercado Pago.
    MP manda varios formatos según la versión:
      - JSON body: {"type": "payment", "data": {"id": "12345"}}
      - Query params: ?topic=payment&id=12345
    """
    topic = body.get("type") or body.get("topic") or query_params.get("topic", [None])[0] or query_params.get("type", [None])[0]
    resource_id = (
        (body.get("data") or {}).get("id")
        or body.get("resource")
        or query_params.get("id", [None])[0]
        or query_params.get("data.id", [None])[0]
    )
    if isinstance(resource_id, str) and resource_id.startswith("http"):
        # En algunos webhooks llega como URL: extraer el id final
        resource_id = urlparse(resource_id).path.rstrip("/").split("/")[-1]
    return (topic or ""), (str(resource_id) if resource_id else None)


def verify_signature(
    x_signature: str | None,
    x_request_id: str | None,
    resource_id: str | None,
) -> bool:
    """
    Valida la firma HMAC del webhook según la doc de MP:
      template = "id:{resource_id};request-id:{x_request_id};ts:{ts};"
      hmac_sha256(secret, template) == hash_recibido

    Si no hay secret configurado, devuelve True (validación deshabilitada — útil en dev).
    """
    secret = os.environ.get("MP_WEBHOOK_SECRET")
    if not secret:
        return True
    if not x_signature or not resource_id:
        return False

    parts = {}
    for chunk in x_signature.split(","):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            parts[k.strip()] = v.strip()
    ts = parts.get("ts")
    received_hash = parts.get("v1")
    if not ts or not received_hash:
        return False

    template = f"id:{resource_id};request-id:{x_request_id or ''};ts:{ts};"
    expected = hmac.new(secret.encode(), template.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received_hash)
