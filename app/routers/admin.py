"""Privacy-preserving aggregate owner stats endpoint protected by ADMIN_STATS_KEY."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import get_settings
from app.database import get_db
from app.security import auth_rate_limiter, utc_now_iso

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _extract_admin_key(x_admin_key: str | None, authorization: str | None) -> str:
    if x_admin_key:
        return x_admin_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return ""


@router.get("/stats")
def owner_aggregate_stats(
    request: Request,
    x_admin_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    """Return aggregate-only account, session, and activity counts (never PII or user content)."""
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else "unknown"
    )
    auth_rate_limiter.check(f"admin_stats:{ip}", limit=20, window_seconds=300)

    expected_key = str(get_settings()["admin_stats_key"])
    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail="Owner stats endpoint is disabled. Set ADMIN_STATS_KEY in environment variables.",
        )

    provided_key = _extract_admin_key(x_admin_key, authorization)
    if not provided_key or not hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid owner stats key.")

    now_iso = utc_now_iso()
    with get_db() as conn:
        verified_accounts = conn.execute(
            "SELECT COUNT(*) FROM users WHERE email_verified = 1 AND is_guest = 0"
        ).fetchone()[0]
        pending_unverified = conn.execute(
            "SELECT COUNT(*) FROM users WHERE email_verified = 0 AND is_guest = 0"
        ).fetchone()[0]
        guest_accounts = conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_guest = 1"
        ).fetchone()[0]
        active_sessions = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE expires_at > ?",
            (now_iso,),
        ).fetchone()[0]
        active_unique_users = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE expires_at > ?",
            (now_iso,),
        ).fetchone()[0]
        sessions_by_method = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT auth_method, COUNT(*) FROM sessions WHERE expires_at > ? GROUP BY auth_method",
                (now_iso,),
            ).fetchall()
        }
        total_mood_scans = conn.execute("SELECT COUNT(*) FROM mood_scans").fetchone()[0]
        total_journal_entries = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
        total_activity_logs = conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0]

    return {
        "as_of_utc": now_iso,
        "users": {
            "verified_accounts": verified_accounts,
            "pending_unverified_accounts": pending_unverified,
            "guest_accounts": guest_accounts,
        },
        "sessions": {
            "active_sessions": active_sessions,
            "active_unique_users": active_unique_users,
            "active_by_method": sessions_by_method,
        },
        "wellness_activity": {
            "total_mood_scans": total_mood_scans,
            "total_journal_entries": total_journal_entries,
            "total_activity_logs": total_activity_logs,
        },
    }
