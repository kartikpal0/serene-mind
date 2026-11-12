"""User profile, gentle onboarding preferences, avatar upload, and data export."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from app.config import UPLOADS_DIR
from app.database import get_db
from app.deps import clear_session_cookie, get_current_user, serialize_user
from app.security import hash_secret, utc_now_iso

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=60)
    avatar_tint: str | None = Field(default=None, max_length=24)
    pronouns: str | None = Field(default=None, max_length=32)
    age_range: str | None = Field(default=None, max_length=24)
    focus_goals: list[str] | None = None
    intention: str | None = Field(default=None, max_length=240)
    tone_preference: str | None = Field(default=None, max_length=16)
    theme_preference: str | None = Field(default=None, max_length=16)
    reminder_enabled: bool | None = None
    reminder_time: str | None = Field(default=None, max_length=8)
    onboarding_completed: bool | None = None
    quick_pin: str | None = Field(default=None, max_length=8)


@router.patch("")
def update_profile(
    payload: ProfileUpdateRequest,
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    """Update gentle profile preferences without friction."""
    user_id = str(current_user["id"])
    updates: list[str] = []
    params: list[object] = []

    if payload.display_name is not None:
        cleaned = payload.display_name.strip()
        if cleaned:
            updates.append("display_name = ?")
            params.append(cleaned)
    if payload.avatar_tint is not None:
        updates.append("avatar_tint = ?")
        params.append(payload.avatar_tint.strip() or "sage")
    if payload.pronouns is not None:
        updates.append("pronouns = ?")
        params.append(payload.pronouns.strip())
    if payload.age_range is not None:
        updates.append("age_range = ?")
        params.append(payload.age_range.strip())
    if payload.focus_goals is not None:
        updates.append("focus_goals_json = ?")
        params.append(json.dumps(payload.focus_goals[:8]))
    if payload.intention is not None:
        updates.append("intention = ?")
        params.append(payload.intention.strip())
    if payload.tone_preference in {"gentle", "clear"}:
        updates.append("tone_preference = ?")
        params.append(payload.tone_preference)
    if payload.theme_preference in {"light", "dark"}:
        updates.append("theme_preference = ?")
        params.append(payload.theme_preference)
    if payload.reminder_enabled is not None:
        updates.append("reminder_enabled = ?")
        params.append(1 if payload.reminder_enabled else 0)
    if payload.reminder_time is not None:
        updates.append("reminder_time = ?")
        params.append(payload.reminder_time.strip() or "20:00")
    if payload.onboarding_completed is not None:
        updates.append("onboarding_completed = ?")
        params.append(1 if payload.onboarding_completed else 0)
    if payload.quick_pin is not None:
        pin_clean = payload.quick_pin.strip()
        if pin_clean == "":
            updates.append("pin_hash = ?")
            params.append("")
        else:
            if not pin_clean.isdigit() or not (4 <= len(pin_clean) <= 8):
                raise HTTPException(status_code=400, detail="Quick PIN must be 4 to 8 digits.")
            updates.append("pin_hash = ?")
            params.append(hash_secret(pin_clean))

    with get_db() as conn:
        if updates:
            params.append(user_id)
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    return {"user": serialize_user(row)}


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    """Upload a calm profile avatar image."""
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file.")

    user_id = str(current_user["id"])
    ext = Path(file.filename or "avatar.png").suffix.lower() or ".png"
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        ext = ".png"
    filename = f"avatar_{uuid.uuid4().hex[:10]}{ext}"
    user_dir = UPLOADS_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Avatar image must be under 5 MB.")
    (user_dir / filename).write_bytes(content)

    with get_db() as conn:
        conn.execute("UPDATE users SET avatar_path = ? WHERE id = ?", (filename, user_id))
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    return {"user": serialize_user(row)}


@router.get("/export")
def export_user_data(current_user: dict[str, object] = Depends(get_current_user)) -> dict[str, object]:
    """Export all personal mood scans, journal entries, and activity logs as JSON."""
    user_id = str(current_user["id"])
    with get_db() as conn:
        moods = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM mood_scans WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        ]
        journals = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM journal_entries WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        ]
        activities = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM activity_logs WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        ]
    return {
        "exported_at": utc_now_iso(),
        "profile": current_user,
        "mood_scans": moods,
        "journal_entries": journals,
        "activity_logs": activities,
    }


@router.delete("")
def delete_account(
    response: Response,
    request: Request,
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, str]:
    """Delete the current user account, session cookie, and all associated media."""
    user_id = str(current_user["id"])
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    user_dir = UPLOADS_DIR / user_id
    if user_dir.exists():
        shutil.rmtree(user_dir, ignore_errors=True)
    clear_session_cookie(response, request=request)
    return {"message": "Account and personal data permanently removed."}
