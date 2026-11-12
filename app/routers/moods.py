"""Mood scanning, manual check-ins, tailored suggestions, and activity logging."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.database import get_db
from app.deps import get_current_user
from app.security import utc_now_iso
from app.wellness_catalog import JOURNAL_PROMPTS, MOOD_CATALOG, get_mood_bundle

router = APIRouter(prefix="/api", tags=["moods"])


class MoodCreateRequest(BaseModel):
    local_date: str = Field(default="")
    time_of_day: str = Field(default="afternoon")
    primary_mood: str = Field(..., min_length=2, max_length=24)
    raw_expression: str = Field(default="neutral", max_length=24)
    wellness_score: int = Field(default=70, ge=0, le=100)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    expressions: dict[str, float] = Field(default_factory=dict)
    source: str = Field(default="face_scan", max_length=24)
    note: str = Field(default="", max_length=400)


class ActivityCreateRequest(BaseModel):
    local_date: str = Field(default="")
    activity_type: str = Field(..., max_length=32)
    title: str = Field(..., max_length=120)
    duration_seconds: int = Field(default=60, ge=0, le=7200)


def _safe_local_date(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) == 10:
        return cleaned
    return datetime.now().strftime("%Y-%m-%d")


@router.get("/moods/catalog")
def mood_catalog(
    mood: str = Query(default="calm"),
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    """Return personalized reflections, activities, and playlists for a mood."""
    tone = str(current_user.get("tone_preference", "gentle"))
    return {
        "bundle": get_mood_bundle(mood, tone),
        "available_moods": [
            {"id": k, "label": v["label"], "tone": v["tone"], "score_base": v["score_base"]}
            for k, v in MOOD_CATALOG.items()
        ],
        "prompts": JOURNAL_PROMPTS,
    }


@router.post("/moods")
def create_mood_scan(
    payload: MoodCreateRequest,
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    """Record a facial mood scan or manual mood check-in tagged by local date."""
    user_id = str(current_user["id"])
    tone = str(current_user.get("tone_preference", "gentle"))
    mood_key = payload.primary_mood.strip().lower()
    if mood_key not in MOOD_CATALOG:
        mood_key = "calm"

    local_date = _safe_local_date(payload.local_date)
    tod = payload.time_of_day if payload.time_of_day in {"morning", "afternoon", "evening", "night"} else "afternoon"
    scan_id = str(uuid.uuid4())
    now = utc_now_iso()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO mood_scans (
                id, user_id, local_date, time_of_day, primary_mood, raw_expression,
                wellness_score, confidence, expressions_json, source, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scan_id,
                user_id,
                local_date,
                tod,
                mood_key,
                payload.raw_expression.strip().lower(),
                payload.wellness_score,
                round(payload.confidence, 3),
                json.dumps(payload.expressions),
                "face_scan" if payload.source == "face_scan" else "manual",
                payload.note.strip(),
                now,
            ),
        )
        row = conn.execute("SELECT * FROM mood_scans WHERE id = ?", (scan_id,)).fetchone()

    item = dict(row)
    item["expressions"] = json.loads(item.pop("expressions_json", "{}") or "{}")
    return {
        "scan": item,
        "bundle": get_mood_bundle(mood_key, tone),
    }


@router.get("/moods")
def list_mood_scans(
    local_date: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    """List recent mood scans, optionally filtered to a specific local_date."""
    user_id = str(current_user["id"])
    with get_db() as conn:
        if local_date.strip():
            rows = conn.execute(
                """
                SELECT * FROM mood_scans
                WHERE user_id = ? AND local_date = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (user_id, local_date.strip(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM mood_scans
                WHERE user_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

    scans = []
    for r in rows:
        item = dict(r)
        item["expressions"] = json.loads(item.pop("expressions_json", "{}") or "{}")
        scans.append(item)

    return {"scans": scans}


@router.post("/activities")
def log_activity(
    payload: ActivityCreateRequest,
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    """Record a completed wellness activity (breathing, grounding, soundscape, playlist)."""
    user_id = str(current_user["id"])
    activity_id = str(uuid.uuid4())
    local_date = _safe_local_date(payload.local_date)
    now = utc_now_iso()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO activity_logs (
                id, user_id, local_date, activity_type, title, duration_seconds, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity_id,
                user_id,
                local_date,
                payload.activity_type.strip(),
                payload.title.strip(),
                payload.duration_seconds,
                now,
            ),
        )
    return {"id": activity_id, "status": "recorded"}
