"""
Helpers para tracking de UTM y eventos.

UTMs se capturan al landing y se guardan en una cookie firmada de 30 días.
Cuando el usuario se registra, los traemos de la cookie a su row en users.
"""
import json
from typing import Optional

from fastapi import Request, Response

from web import db

UTM_COOKIE = "vtia_attrib"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 días


def capture_utm_from_request(request: Request, response: Response):
    """
    Llamar al landing y otras vistas públicas.
    Si la URL tiene utm_*, guardar en cookie (sobrescribe si llegaron nuevos UTMs).
    También captura referrer si no había uno previo.
    """
    qp = request.query_params
    utm_source = qp.get("utm_source")
    utm_medium = qp.get("utm_medium")
    utm_campaign = qp.get("utm_campaign")

    # Si no hay nada nuevo, no hacemos nada
    if not (utm_source or utm_medium or utm_campaign):
        return

    referrer = request.headers.get("referer") or ""

    payload = {
        "utm_source": utm_source or "",
        "utm_medium": utm_medium or "",
        "utm_campaign": utm_campaign or "",
        "referrer": referrer[:300],
    }
    response.set_cookie(
        UTM_COOKIE,
        json.dumps(payload, separators=(",", ":")),
        max_age=COOKIE_MAX_AGE,
        httponly=False,
        samesite="lax",
    )


def read_utm_cookie(request: Request) -> dict:
    raw = request.cookies.get(UTM_COOKIE)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def attach_utm_to_user(request: Request, user_id: int):
    """Llamar después del registro para asociar los UTMs al user."""
    data = read_utm_cookie(request)
    if not data:
        return
    db.set_user_utm(
        user_id=user_id,
        utm_source=data.get("utm_source", "") or "",
        utm_medium=data.get("utm_medium", "") or "",
        utm_campaign=data.get("utm_campaign", "") or "",
        referrer=data.get("referrer", "") or "",
    )


def log_event(
    request: Request,
    event_type: str,
    user_id: Optional[int] = None,
    metadata: Optional[dict] = None,
):
    """Wrapper que enriquece el evento con UTMs de la cookie y referrer."""
    data = read_utm_cookie(request)
    db.log_event(
        event_type=event_type,
        user_id=user_id,
        utm_source=data.get("utm_source") or None,
        utm_medium=data.get("utm_medium") or None,
        utm_campaign=data.get("utm_campaign") or None,
        referrer=(request.headers.get("referer") or data.get("referrer") or "")[:300] or None,
        metadata=metadata,
    )
