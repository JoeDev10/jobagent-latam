"""
Base de datos de usuarios del SaaS.
Tablas: users, user_profiles, user_settings
Usa sqlite3 puro — sin ORM.
"""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
DB_PATH = _data_dir / "users.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate(conn: sqlite3.Connection):
    migrations = [
        ("users",          "runs_used",           "INTEGER DEFAULT 0"),
        ("users",          "upgraded_at",         "TEXT"),
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
