"""Daily digital journal with text, photos, voice notes, midnight reset, and 8 PM reminders."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import UPLOADS_DIR
from app.database import get_db
from app.deps import get_current_user
from app.mail_service import send_email_message
from app.security import utc_now_iso
from app.wellness_catalog import JOURNAL_PROMPTS

router = APIRouter(prefix="/api", tags=["journal"])


class JournalUpdateRequest(BaseModel):
    content: str | None = Field(default=None, max_length=10000)
    gratitude_note: str | None = Field(default=None, max_length=1000)
    mood_tag: str | None = Field(default=None, max_length=24)


class ReminderCheckRequest(BaseModel):
    local_date: str = Field(...)
    local_time: str = Field(...)
    force_preview: bool = Field(default=False)


def _safe_local_date(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) == 10:
        return cleaned
    return datetime.now().strftime("%Y-%m-%d")


def _hydrate_entries(conn: Any, user_id: str, rows: list[Any]) -> list[dict[str, Any]]:
    if not rows:
        return []
    entry_ids = [r["id"] for r in rows]
    placeholders = ",".join("?" for _ in entry_ids)
    media_rows = conn.execute(
        f"SELECT * FROM journal_media WHERE entry_id IN ({placeholders}) ORDER BY created_at ASC",
        entry_ids,
    ).fetchall()

    media_by_entry: dict[str, list[dict[str, Any]]] = {}
    for m in media_rows:
        media_item = dict(m)
        media_item["url"] = f"/api/media/{user_id}/{m['file_path']}"
        media_by_entry.setdefault(m["entry_id"], []).append(media_item)

    result = []
    for row in rows:
        entry = dict(row)
        entry["media"] = media_by_entry.get(row["id"], [])
        result.append(entry)
    return result


@router.get("/journal")
def get_journal_for_day(
    local_date: str = Query(default=""),
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    """Return journal entries for a given local date (supporting daily midnight canvas)."""
    user_id = str(current_user["id"])
    target_date = _safe_local_date(local_date)

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM journal_entries
            WHERE user_id = ? AND local_date = ?
            ORDER BY created_at DESC
            """,
            (user_id, target_date),
        ).fetchall()
        entries = _hydrate_entries(conn, user_id, rows)

    return {
        "local_date": target_date,
        "written_today": len(entries) > 0,
        "count": len(entries),
        "entries": entries,
        "prompts": JOURNAL_PROMPTS,
    }


@router.get("/journal/days")
def list_journal_days(
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    """Return all past & present dates that contain journal entries or mood scans."""
    user_id = str(current_user["id"])
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT local_date,
                   COUNT(*) AS entry_count,
                   MAX(mood_tag) AS last_mood
            FROM journal_entries
            WHERE user_id = ?
            GROUP BY local_date
            ORDER BY local_date DESC
            LIMIT 120
            """,
            (user_id,),
        ).fetchall()
    return {"days": [dict(r) for r in rows]}


@router.post("/journal")
async def create_journal_entry(
    local_date: str = Form(default=""),
    time_of_day: str = Form(default="evening"),
    mood_tag: str = Form(default="calm"),
    prompt_used: str = Form(default=""),
    content: str = Form(default=""),
    gratitude_note: str = Form(default=""),
    audio_duration: float = Form(default=0.0),
    photos: list[UploadFile] = File(default=[]),
    audio: UploadFile | None = File(default=None),
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    """Create a journal entry with optional text, multiple photos, and voice recording."""
    cleaned_text = content.strip()
    cleaned_gratitude = gratitude_note.strip()
    valid_photos = [p for p in photos if p.filename]
    has_audio = audio is not None and bool(audio.filename)

    if not cleaned_text and not cleaned_gratitude and not valid_photos and not has_audio:
        raise HTTPException(
            status_code=400,
            detail="Add a thought, gratitude note, photo, or voice recording before saving.",
        )

    user_id = str(current_user["id"])
    entry_id = str(uuid.uuid4())
    target_date = _safe_local_date(local_date)
    tod = time_of_day if time_of_day in {"morning", "afternoon", "evening", "night"} else "evening"
    now = utc_now_iso()

    user_dir = UPLOADS_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    saved_media: list[tuple[str, str, str, str, float]] = []

    for photo in valid_photos[:6]:
        raw_bytes = await photo.read()
        if not raw_bytes:
            continue
        if len(raw_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Each photo must be under 10 MB.")
        ext = Path(photo.filename or "photo.jpg").suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            ext = ".jpg"
        filename = f"img_{uuid.uuid4().hex[:12]}{ext}"
        (user_dir / filename).write_bytes(raw_bytes)
        saved_media.append(
            (str(uuid.uuid4()), "image", filename, photo.content_type or "image/jpeg", 0.0)
        )

    if has_audio and audio is not None:
        audio_bytes = await audio.read()
        if audio_bytes:
            if len(audio_bytes) > 25 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="Voice recording must be under 25 MB.")
            ext = Path(audio.filename or "voice.webm").suffix.lower()
            if ext not in {".webm", ".ogg", ".mp4", ".m4a", ".wav", ".mp3"}:
                ext = ".webm"
            filename = f"voice_{uuid.uuid4().hex[:12]}{ext}"
            (user_dir / filename).write_bytes(audio_bytes)
            saved_media.append(
                (
                    str(uuid.uuid4()),
                    "audio",
                    filename,
                    audio.content_type or "audio/webm",
                    float(audio_duration or 0.0),
                )
            )

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO journal_entries (
                id, user_id, local_date, time_of_day, mood_tag, prompt_used,
                content, gratitude_note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                user_id,
                target_date,
                tod,
                mood_tag.strip().lower() or "calm",
                prompt_used.strip(),
                cleaned_text,
                cleaned_gratitude,
                now,
                now,
            ),
        )
        for media_id, media_type, filename, mime_type, duration in saved_media:
            conn.execute(
                """
                INSERT INTO journal_media (
                    id, entry_id, user_id, media_type, file_path, mime_type,
                    duration_seconds, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (media_id, entry_id, user_id, media_type, filename, mime_type, duration, now),
            )
        row = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
        entry = _hydrate_entries(conn, user_id, [row])[0]

    return {"entry": entry}


@router.patch("/journal/{entry_id}")
def update_journal_entry(
    entry_id: str,
    payload: JournalUpdateRequest,
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    """Update text, gratitude note, or mood tag on an existing journal entry."""
    user_id = str(current_user["id"])
    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM journal_entries WHERE id = ? AND user_id = ?",
            (entry_id, user_id),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Journal entry not found.")

        new_content = payload.content.strip() if payload.content is not None else existing["content"]
        new_gratitude = (
            payload.gratitude_note.strip()
            if payload.gratitude_note is not None
            else existing["gratitude_note"]
        )
        new_mood = (
            payload.mood_tag.strip().lower() if payload.mood_tag is not None else existing["mood_tag"]
        )
        conn.execute(
            """
            UPDATE journal_entries
            SET content = ?, gratitude_note = ?, mood_tag = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (new_content, new_gratitude, new_mood, utc_now_iso(), entry_id, user_id),
        )
        row = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
        entry = _hydrate_entries(conn, user_id, [row])[0]

    return {"entry": entry}


@router.delete("/journal/{entry_id}")
def delete_journal_entry(
    entry_id: str,
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, str]:
    """Delete a journal entry and any attached photo or audio files."""
    user_id = str(current_user["id"])
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM journal_entries WHERE id = ? AND user_id = ?",
            (entry_id, user_id),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Journal entry not found.")

        media_rows = conn.execute(
            "SELECT file_path FROM journal_media WHERE entry_id = ? AND user_id = ?",
            (entry_id, user_id),
        ).fetchall()
        conn.execute("DELETE FROM journal_entries WHERE id = ? AND user_id = ?", (entry_id, user_id))

    for m in media_rows:
        target = UPLOADS_DIR / user_id / Path(m["file_path"]).name
        if target.exists():
            target.unlink(missing_ok=True)

    return {"message": "Journal entry removed."}


@router.get("/media/{user_id}/{filename}")
def get_user_media(
    user_id: str,
    filename: str,
    current_user: dict[str, object] = Depends(get_current_user),
) -> FileResponse:
    """Serve private uploaded photos, voice recordings, and avatars only to their owner."""
    if str(current_user["id"]) != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    user_dir = (UPLOADS_DIR / user_id).resolve()
    target = (user_dir / safe_name).resolve()
    if not target.is_relative_to(user_dir):
        raise HTTPException(status_code=400, detail="Invalid path.")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Media file not found.")
    return FileResponse(target, headers={"Cache-Control": "private, no-store"})


@router.post("/reminders/check")
def check_evening_reminder(
    payload: ReminderCheckRequest,
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    """Determine whether the 8 PM unwritten-journal notification should fire today."""
    user_id = str(current_user["id"])
    local_date = _safe_local_date(payload.local_date)
    local_time = payload.local_time.strip()
    reminder_time = str(current_user.get("reminder_time") or "20:00")
    enabled = bool(current_user.get("reminder_enabled", True))

    with get_db() as conn:
        count_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM journal_entries WHERE user_id = ? AND local_date = ?",
            (user_id, local_date),
        ).fetchone()
        written_today = int(count_row["cnt"]) > 0

        user_row = conn.execute(
            "SELECT email, display_name, last_reminded_date FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        already_reminded = user_row["last_reminded_date"] == local_date

        is_time_due = local_time >= reminder_time
        should_notify = payload.force_preview or (
            enabled and not written_today and is_time_due and not already_reminded
        )

        if should_notify and not payload.force_preview:
            conn.execute(
                "UPDATE users SET last_reminded_date = ? WHERE id = ?",
                (local_date, user_id),
            )
            send_email_message(
                conn,
                recipient=user_row["email"],
                subject="Your quiet 8 PM Serene check-in",
                body_text=(
                    f"Hi {user_row['display_name']},\n\n"
                    "You haven't added a journal reflection today yet. "
                    "Before midnight resets your daily canvas, take two quiet minutes to write, "
                    "snap a moment, or leave a short voice note."
                ),
            )

    return {
        "should_notify": should_notify,
        "written_today": written_today,
        "reminder_enabled": enabled,
        "reminder_time": reminder_time,
        "title": "Evening Check-in (8:00 PM)",
        "body": "Your daily journal is still open for today. Take two quiet minutes before midnight resets the canvas.",
    }
