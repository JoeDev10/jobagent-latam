"""
Auth helpers: hash de contraseñas y tokens de sesión firmados con HMAC.
Sin dependencias externas — usa solo stdlib.
"""
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Cookie, Request
from fastapi.responses import RedirectResponse

SECRET_KEY = os.environ.get("SECRET_KEY", "jobagent-latam-saas-secret-2026-cambiar-en-prod")
TOKEN_EXPIRE_DAYS = 30


# ─── Contraseñas ──────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, dk_hex = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ─── Tokens ───────────────────────────────────────────────────────────────────

def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": (datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)).isoformat(),
    }
    data = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(SECRET_KEY.encode(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}.{sig}"


def verify_token(token: str) -> Optional[dict]:
    try:
        data, sig = token.rsplit(".", 1)
        expected = hmac.new(SECRET_KEY.encode(), data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        padding = "=" * (-len(data) % 4)
        payload = json.loads(base64.urlsafe_b64decode(data + padding).decode())
        if datetime.fromisoformat(payload["exp"]) < datetime.utcnow():
            return None
        return payload
    except Exception:
        return None


# ─── Dependencia de FastAPI ────────────────────────────────────────────────────

def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("session")
    if not token:
        return None
    return verify_token(token)


def require_auth(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise _redirect_to_login()
    return user


class _redirect_to_login(Exception):
    pass
