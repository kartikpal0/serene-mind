"""Shared authentication dependencies and user serialization."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import Cookie, Header, HTTPException, Request, Response

from app.database import get_db
from app.security import SESSION_COOKIE_NAME, hash_token


def serialize_user(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a SQLite user row to a safe API response dictionary."""
    return {
        "id": row["id"],
        "email": row["email"],
        "email_verified": bool(row["email_verified"]),
        "display_name": row["display_name"],
        "avatar_tint": row["avatar_tint"],
        "avatar_url": f"/api/media/{row['id']}/{row['avatar_path']}" if row["avatar_path"] else "",
        "pronouns": row["pronouns"],
        "age_range": row["age_range"],
        "focus_goals": json.loads(row["focus_goals_json"] or "[]"),
        "intention": row["intention"],
        "tone_preference": row["tone_preference"],
        "theme_preference": row["theme_preference"],
        "reminder_enabled": bool(row["reminder_enabled"]),
        "reminder_time": row["reminder_time"],
        "has_pin": bool(row["pin_hash"]),
        "has_password": bool(row["password_hash"]),
        "onboarding_completed": bool(row["onboarding_completed"]),
        "is_guest": bool(row["is_guest"]),
        "last_reminded_date": row["last_reminded_date"],
        "created_at": row["created_at"],
    }


def is_https_request(request: Request | None) -> bool:
    """Determine whether the incoming request arrived over HTTPS (including reverse proxies)."""
    if request is None:
        return False
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if proto == "https":
        return True
    return request.url.scheme == "https"


def set_session_cookie(response: Response, raw_token: str, request: Request | None = None) -> None:
    """Attach the session cookie with HttpOnly, SameSite, and Secure on HTTPS."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        samesite="lax",
        secure=is_https_request(request),
        max_age=30 * 24 * 60 * 60,
        path="/",
    )


def clear_session_cookie(response: Response, request: Request | None = None) -> None:
    """Clear the session cookie."""
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=is_https_request(request),
        samesite="lax",
    )


def extract_session_token(
    cookie_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> str | None:
    """Read session token from HTTP-only cookie or Bearer header."""
    if cookie_token:
        return cookie_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def get_current_user(
    cookie_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Resolve and validate the currently authenticated user."""
    raw_token = extract_session_token(cookie_token, authorization)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Not signed in.")

    token_hash = hash_token(raw_token)
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT u.*, s.expires_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Session expired or invalid.")

        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at < datetime.now(timezone.utc):
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            raise HTTPException(status_code=401, detail="Session expired.")

        return serialize_user(row)
