"""
Base de datos de usuarios del SaaS.
Tablas: users, user_profiles, user_settings
Usa sqlite3 local o Turso (SQLite en la nube) según env vars.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

_TURSO_URL = os.environ.get("TURSO_DATABASE_URL")
_TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

import sqlite3  # always needed for IntegrityError, OperationalError
try:
    import libsql_experimental as _libsql
except Exception:
    _libsql = None
    _TURSO_URL = None  # disable Turso if library missing

_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
DB_PATH = _data_dir / "users.db"
_TURSO_DISABLED = False  # flips to True if first connect fails -> fallback to local SQLite


class _TursoCur:
    """Cursor wrapper that returns dicts (libsql_experimental has no row_factory)."""
    def __init__(self, cur):
        self._c = cur

    @property
    def lastrowid(self):
        return getattr(self._c, "lastrowid", None)

    @property
    def description(self):
        return getattr(self._c, "description", None)

    def _row_to_dict(self, row):
        desc = self.description
        if row is None or not desc:
            return row
        return {col[0]: row[i] for i, col in enumerate(desc)}

    def fetchone(self):
        return self._row_to_dict(self._c.fetchone())

    def fetchall(self):
        rows = self._c.fetchall()
        if not rows:
            return []
        return [self._row_to_dict(r) for r in rows]


class _TursoConn:
    """Connection wrapper for libsql_experimental."""
    def __init__(self, conn):
        self._c = conn

    def execute(self, sql, params=()):
        return _TursoCur(self._c.execute(sql, params))

    def executescript(self, script):
        for stmt in script.split(";"):
            stmt = stmt.strip()
            if stmt and not stmt.startswith("--"):
                try:
                    self._c.execute(stmt)
                except Exception:
                    pass
        self._c.commit()

    def commit(self):
        self._c.commit()

    def close(self):
        try:
            self._c.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            try:
                self._c.commit()
            except Exception:
                pass
        self.close()


def _connect_local():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = lambda cur, row: {col[0]: row[idx] for idx, col in enumerate(cur.description)}
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _connect():
    global _TURSO_DISABLED
    if _TURSO_URL and _libsql and not _TURSO_DISABLED:
        try:
            conn = _libsql.connect(_TURSO_URL, auth_token=_TURSO_TOKEN)
            try:
                conn.execute("PRAGMA foreign_keys=ON")
            except Exception:
                pass
            return _TursoConn(conn)
        except Exception as e:
            print(f"[WARN] Turso connect failed, fallback to local SQLite: {e}", flush=True)
            _TURSO_DISABLED = True
    return _connect_local()


def _migrate(conn: sqlite3.Connection):
    migrations = [
        ("users",          "runs_used",           "INTEGER DEFAULT 0"),
        ("users",          "upgraded_at",         "TEXT"),
        ("users",          "utm_source",          "TEXT"),
        ("users",          "utm_medium",          "TEXT"),
        ("users",          "utm_campaign",        "TEXT"),
        ("users",          "referrer",            "TEXT"),
        ("user_settings",  "zonajobs_email",      "TEXT DEFAULT ''"),
        ("user_settings",  "zonajobs_password",   "TEXT DEFAULT ''"),
    ]
    for table, col, defval in migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defval}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists


def init_db():
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                email       TEXT UNIQUE NOT NULL,
                password    TEXT NOT NULL,
                full_name   TEXT NOT NULL,
                plan        TEXT DEFAULT 'free',
                runs_used   INTEGER DEFAULT 0,
                upgraded_at TEXT,
                created_at  TEXT NOT NULL,
                last_login  TEXT
            );

            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id      INTEGER PRIMARY KEY,
                profile_json TEXT,
                updated_at   TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token      TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                used       INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_settings (
                user_id                 INTEGER PRIMARY KEY,
                computrabajo_email      TEXT DEFAULT '',
                computrabajo_password   TEXT DEFAULT '',
                bumeran_email           TEXT DEFAULT '',
                bumeran_password        TEXT DEFAULT '',
                groq_api_key            TEXT DEFAULT '',
                telegram_bot_token      TEXT DEFAULT '',
                telegram_chat_id        TEXT DEFAULT '',
                max_apps_per_day        INTEGER DEFAULT 30,
                auto_apply_threshold    REAL DEFAULT 0.80,
                min_score               REAL DEFAULT 0.60,
                headless                INTEGER DEFAULT 1,
                preferred_portals       TEXT DEFAULT '["computrabajo"]',
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS payments (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id             INTEGER NOT NULL,
                mp_payment_id       TEXT UNIQUE,
                mp_preference_id    TEXT,
                external_reference  TEXT,
                amount              REAL,
                currency            TEXT DEFAULT 'ARS',
                status              TEXT,
                status_detail       TEXT,
                payer_email         TEXT,
                raw_payload         TEXT,
                created_at          TEXT NOT NULL,
                updated_at          TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_payments_user   ON payments(user_id);
            CREATE INDEX IF NOT EXISTS idx_payments_mp_id  ON payments(mp_payment_id);
            CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);

            CREATE TABLE IF NOT EXISTS events (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER,
                event_type    TEXT NOT NULL,
                utm_source    TEXT,
                utm_medium    TEXT,
                utm_campaign  TEXT,
                referrer      TEXT,
                metadata      TEXT,
                created_at    TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_user      ON events(user_id);
            CREATE INDEX IF NOT EXISTS idx_events_type      ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_created   ON events(created_at);
            CREATE INDEX IF NOT EXISTS idx_events_utm       ON events(utm_source);
        """)
        conn.commit()
        _migrate(conn)


# ─── Usuarios ─────────────────────────────────────────────────────────────────

def create_user(email: str, password_hash: str, full_name: str) -> Optional[int]:
    try:
        with _connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, password, full_name, created_at) VALUES (?,?,?,?)",
                (email.lower().strip(), password_hash, full_name, datetime.now().isoformat()),
            )
            uid = cur.lastrowid
            conn.execute("INSERT INTO user_settings (user_id) VALUES (?)", (uid,))
            conn.commit()
            return uid
    except sqlite3.IntegrityError:
        return None


def get_user_by_email(email: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def increment_run_count(user_id: int):
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET runs_used = COALESCE(runs_used, 0) + 1 WHERE id = ?",
            (user_id,),
        )
        conn.commit()


def set_user_plan(user_id: int, plan: str):
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET plan = ?, upgraded_at = ? WHERE id = ?",
            (plan, datetime.now().isoformat(), user_id),
        )
        conn.commit()


def update_last_login(user_id: int):
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.now().isoformat(), user_id),
        )
        conn.commit()


# ─── Perfil ───────────────────────────────────────────────────────────────────

def save_profile(user_id: int, profile: dict):
    with _connect() as conn:
        conn.execute(
            """INSERT INTO user_profiles (user_id, profile_json, updated_at)
               VALUES (?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 profile_json = excluded.profile_json,
                 updated_at   = excluded.updated_at""",
            (user_id, json.dumps(profile, ensure_ascii=False), datetime.now().isoformat()),
        )
        conn.commit()


def get_profile(user_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT profile_json FROM user_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row and row["profile_json"]:
            return json.loads(row["profile_json"])
        return None


# ─── Settings ─────────────────────────────────────────────────────────────────

def get_settings(user_id: int) -> dict:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            d = dict(row)
            d["preferred_portals"] = json.loads(d.get("preferred_portals") or '["computrabajo"]')
            return d
        return {}


def update_settings(user_id: int, **kwargs):
    if not kwargs:
        return
    if "preferred_portals" in kwargs and isinstance(kwargs["preferred_portals"], list):
        kwargs["preferred_portals"] = json.dumps(kwargs["preferred_portals"])
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [user_id]
    with _connect() as conn:
        conn.execute(f"UPDATE user_settings SET {cols} WHERE user_id = ?", vals)
        conn.commit()


def get_user_count() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        return row["c"] if row else 0


def get_all_users() -> list:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, email, full_name, plan, runs_used, created_at, last_login FROM users ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def update_password(user_id: int, password_hash: str):
    with _connect() as conn:
        conn.execute("UPDATE users SET password = ? WHERE id = ?", (password_hash, user_id))
        conn.commit()


# ─── Password reset tokens ────────────────────────────────────────────────────

def create_reset_token(user_id: int, token: str, expires_at: str):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO password_reset_tokens (token, user_id, expires_at, created_at) VALUES (?,?,?,?)",
            (token, user_id, expires_at, datetime.now().isoformat()),
        )
        conn.commit()


def get_reset_token(token: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM password_reset_tokens WHERE token = ? AND used = 0",
            (token,),
        ).fetchone()
        return dict(row) if row else None


def mark_token_used(token: str):
    with _connect() as conn:
        conn.execute("UPDATE password_reset_tokens SET used = 1 WHERE token = ?", (token,))
        conn.commit()


# ─── Pagos Mercado Pago ───────────────────────────────────────────────────────

def save_payment_preference(user_id: int, preference_id: str, external_reference: str, amount: float) -> int:
    """Registra una preferencia creada antes del checkout. Devuelve el id local."""
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO payments (user_id, mp_preference_id, external_reference, amount, status, created_at)
               VALUES (?,?,?,?,?,?)""",
            (user_id, preference_id, external_reference, amount, "pending", datetime.now().isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def upsert_payment(mp_payment_id: str, user_id: int, payload: dict) -> tuple[bool, bool]:
    """
    Inserta o actualiza un pago. Devuelve (created, already_approved):
      - created: True si es la primera vez que vemos este mp_payment_id
      - already_approved: True si ya estaba marcado como approved (para evitar upgrade duplicado)
    """
    now = datetime.now().isoformat()
    status = payload.get("status", "")
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, status FROM payments WHERE mp_payment_id = ?", (mp_payment_id,)
        ).fetchone()
        if row:
            already_approved = row["status"] == "approved"
            conn.execute(
                """UPDATE payments SET status=?, status_detail=?, payer_email=?, raw_payload=?, updated_at=?
                   WHERE id=?""",
                (
                    status,
                    payload.get("status_detail"),
                    (payload.get("payer") or {}).get("email"),
                    json.dumps(payload, ensure_ascii=False)[:8000],
                    now,
                    row["id"],
                ),
            )
            conn.commit()
            return False, already_approved
        conn.execute(
            """INSERT INTO payments
                 (user_id, mp_payment_id, mp_preference_id, external_reference, amount, currency,
                  status, status_detail, payer_email, raw_payload, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                user_id,
                mp_payment_id,
                payload.get("preference_id"),
                payload.get("external_reference"),
                payload.get("transaction_amount"),
                payload.get("currency_id", "ARS"),
                status,
                payload.get("status_detail"),
                (payload.get("payer") or {}).get("email"),
                json.dumps(payload, ensure_ascii=False)[:8000],
                now,
                now,
            ),
        )
        conn.commit()
        return True, False


def get_user_payments(user_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM payments WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Tracking / Analytics ─────────────────────────────────────────────────────

def log_event(
    event_type: str,
    user_id: Optional[int] = None,
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    referrer: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    """Loguea un evento. No falla si la DB está caída — el tracking nunca debe romper UX."""
    try:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO events (user_id, event_type, utm_source, utm_medium, utm_campaign, referrer, metadata, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    user_id,
                    event_type,
                    utm_source,
                    utm_medium,
                    utm_campaign,
                    referrer,
                    json.dumps(metadata, ensure_ascii=False) if metadata else None,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
    except Exception:
        pass  # tracking is best-effort


def set_user_utm(user_id: int, utm_source: str, utm_medium: str, utm_campaign: str, referrer: str):
    """Asocia UTMs al usuario al registrarse (solo si los campos están vacíos)."""
    with _connect() as conn:
        conn.execute(
            """UPDATE users
               SET utm_source = COALESCE(NULLIF(utm_source, ''), ?),
                   utm_medium = COALESCE(NULLIF(utm_medium, ''), ?),
                   utm_campaign = COALESCE(NULLIF(utm_campaign, ''), ?),
                   referrer = COALESCE(NULLIF(referrer, ''), ?)
               WHERE id = ?""",
            (utm_source or None, utm_medium or None, utm_campaign or None, referrer or None, user_id),
        )
        conn.commit()


def metrics_funnel(days: int = 7) -> dict:
    """Conteo de eventos clave en los últimos N días."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT event_type, COUNT(*) AS c
               FROM events
               WHERE created_at >= datetime('now', ?)
               GROUP BY event_type""",
            (f"-{days} days",),
        ).fetchall()
        return {r["event_type"]: r["c"] for r in rows}


def metrics_by_utm(days: int = 7) -> list[dict]:
    """Breakdown de registros por utm_source en los últimos N días."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT COALESCE(utm_source, 'direct') AS source,
                      COALESCE(utm_medium, '-')     AS medium,
                      COALESCE(utm_campaign, '-')   AS campaign,
                      COUNT(*) AS users
               FROM users
               WHERE created_at >= datetime('now', ?)
               GROUP BY source, medium, campaign
               ORDER BY users DESC""",
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]


def metrics_daily_signups(days: int = 14) -> list[dict]:
    """Registros por día — para gráfico de cohort."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT DATE(created_at) AS day, COUNT(*) AS users
               FROM users
               WHERE created_at >= datetime('now', ?)
               GROUP BY day
               ORDER BY day""",
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]


def metrics_conversion_funnel() -> list[dict]:
    """
    Funnel: % de usuarios que pasaron por cada paso.
    Cuenta usuarios únicos (no eventos) en cada step.
    """
    steps = [
        ("Registros", "SELECT COUNT(*) FROM users"),
        ("Onboarding completado", "SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type='onboarding_completed'"),
        ("Primera búsqueda", "SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type='first_search'"),
        ("Vio /upgrade", "SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type='upgrade_viewed'"),
        ("Inició pago", "SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type='payment_started'"),
        ("Es Pro", "SELECT COUNT(*) FROM users WHERE plan='pro'"),
    ]
    result = []
    with _connect() as conn:
        first = None
        for label, sql in steps:
            row = conn.execute(sql).fetchone()
            count = row[0] if row else 0
            if first is None:
                first = count
            pct = (count / first * 100) if first else 0
            result.append({"step": label, "count": count, "pct": round(pct, 1)})
    return result
