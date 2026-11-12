"""SQLite database initialization, safe migrations, and connection helpers."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app import config


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    email_verified INTEGER NOT NULL DEFAULT 0,
    display_name TEXT NOT NULL,
    avatar_tint TEXT NOT NULL DEFAULT 'sage',
    avatar_path TEXT NOT NULL DEFAULT '',
    pronouns TEXT NOT NULL DEFAULT '',
    age_range TEXT NOT NULL DEFAULT '',
    focus_goals_json TEXT NOT NULL DEFAULT '[]',
    intention TEXT NOT NULL DEFAULT '',
    tone_preference TEXT NOT NULL DEFAULT 'gentle',
    theme_preference TEXT NOT NULL DEFAULT 'light',
    reminder_enabled INTEGER NOT NULL DEFAULT 1,
    reminder_time TEXT NOT NULL DEFAULT '20:00',
    pin_hash TEXT NOT NULL DEFAULT '',
    onboarding_completed INTEGER NOT NULL DEFAULT 0,
    is_guest INTEGER NOT NULL DEFAULT 0,
    last_reminded_date TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    auth_method TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS auth_codes (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    purpose TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    link_token_hash TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dev_outbox (
    id TEXT PRIMARY KEY,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body_text TEXT NOT NULL,
    action_url TEXT NOT NULL DEFAULT '',
    otp_or_token TEXT NOT NULL DEFAULT '',
    delivery_mode TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mood_scans (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    local_date TEXT NOT NULL,
    time_of_day TEXT NOT NULL,
    primary_mood TEXT NOT NULL,
    raw_expression TEXT NOT NULL DEFAULT 'neutral',
    wellness_score INTEGER NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    expressions_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'manual',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_mood_scans_user_date
    ON mood_scans(user_id, local_date);

CREATE TABLE IF NOT EXISTS journal_entries (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    local_date TEXT NOT NULL,
    time_of_day TEXT NOT NULL,
    mood_tag TEXT NOT NULL DEFAULT 'calm',
    prompt_used TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    gratitude_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_journal_entries_user_date
    ON journal_entries(user_id, local_date);

CREATE TABLE IF NOT EXISTS journal_media (
    id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    media_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    duration_seconds REAL NOT NULL DEFAULT 0,
    caption TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (entry_id) REFERENCES journal_entries(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    local_date TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    title TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_user_date
    ON activity_logs(user_id, local_date);
"""


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """Safely add a column to an existing SQLite table if missing."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_storage_dirs() -> None:
    """Create database and media upload directories if missing."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    """Initialize SQLite tables, indexes, and forward-compatible column migrations."""
    ensure_storage_dirs()
    with sqlite3.connect(config.DB_PATH, check_same_thread=False) as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_column(conn, "users", "email_verified", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "auth_codes", "link_token_hash", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "auth_codes", "attempts", "INTEGER NOT NULL DEFAULT 0")
        conn.commit()


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection configured with row factory and foreign keys."""
    ensure_storage_dirs()
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
