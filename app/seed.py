"""Demo guest account seeding so visitors can explore multi-day analytics right away."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta


def seed_guest_history(conn: sqlite3.Connection, user_id: str, today_str: str) -> None:
    """Populate 13 prior days of calm mood scans, journal entries, and activities for a guest user.

    Note: Leaves `today_str` open without a journal entry so the user can test
    writing today's journal and seeing the 8 PM reminder state!
    """
    try:
        today_date = datetime.strptime(today_str, "%Y-%m-%d").date()
    except ValueError:
        today_date = datetime.now().date()

    sample_days = [
        (13, "stressed", "angry", 46, "morning", "Busy start to the week, shoulders felt tight.", "Morning coffee still smelled wonderful.", True),
        (12, "anxious", "fearful", 49, "afternoon", "Worried about upcoming deadlines.", "Took a quiet 10-minute walk around the block.", True),
        (11, "calm", "neutral", 66, "evening", "Felt steadier after breathing exercises.", "Quiet evening rain outside the window.", True),
        (10, "happy", "happy", 84, "afternoon", "Caught up with an old friend over lunch.", "Laughter always shifts my whole posture.", True),
        (9, "calm", "neutral", 74, "morning", "Slow morning stretch helped a lot.", "Fresh air on the balcony.", False),
        (8, "sad", "sad", 41, "evening", "Felt a wave of loneliness after work.", "Allowed myself an early bedtime without guilt.", True),
        (7, "tired", "neutral", 55, "morning", "Low energy after poor sleep.", "Warm herbal tea at 3 PM.", True),
        (6, "calm", "neutral", 72, "afternoon", "Energy returning slowly. Focused well.", "Finished reading two chapters.", True),
        (5, "happy", "happy", 86, "evening", "Creative flow clicked in the afternoon.", "Sunset colors across the street.", True),
        (4, "happy", "happy", 89, "morning", "Woke up rested and genuinely optimistic.", "Grateful for slow weekend mornings.", True),
        (3, "anxious", "fearful", 54, "evening", "Sunday evening anticipation creeping in.", "4-7-8 breathing brought my heart rate down.", True),
        (2, "calm", "neutral", 76, "afternoon", "Balanced pace throughout Monday.", "Said no to an extra meeting.", True),
        (1, "happy", "happy", 82, "evening", "Warm evening reflection and felt calmer.", "Grateful for small consistent habits.", True),
    ]

    for days_ago, mood, raw_expr, score, tod, note, gratitude, has_journal in sample_days:
        day = today_date - timedelta(days=days_ago)
        day_str = day.isoformat()
        hour = {"morning": 9, "afternoon": 14, "evening": 20}.get(tod, 12)
        ts = f"{day_str}T{hour:02d}:15:00+00:00"

        expressions = {
            "happy": 0.72 if mood == "happy" else 0.12,
            "neutral": 0.75 if mood in {"calm", "tired"} else 0.18,
            "sad": 0.68 if mood == "sad" else 0.05,
            "angry": 0.61 if mood == "stressed" else 0.04,
            "fearful": 0.58 if mood == "anxious" else 0.05,
            "disgusted": 0.02,
            "surprised": 0.04,
        }

        conn.execute(
            """
            INSERT INTO mood_scans (
                id, user_id, local_date, time_of_day, primary_mood, raw_expression,
                wellness_score, confidence, expressions_json, source, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                user_id,
                day_str,
                tod,
                mood,
                raw_expr,
                score,
                0.86,
                json.dumps(expressions),
                "face_scan",
                note,
                ts,
            ),
        )

        if has_journal:
            conn.execute(
                """
                INSERT INTO journal_entries (
                    id, user_id, local_date, time_of_day, mood_tag, prompt_used,
                    content, gratitude_note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    user_id,
                    day_str,
                    tod,
                    mood,
                    "What felt surprisingly light or comforting today?",
                    note,
                    gratitude,
                    ts,
                    ts,
                ),
            )

        if score < 70 or days_ago % 2 == 0:
            conn.execute(
                """
                INSERT INTO activity_logs (
                    id, user_id, local_date, activity_type, title, duration_seconds, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    user_id,
                    day_str,
                    "breathing" if score < 60 else "soundscape",
                    "4-7-8 Nervous System Reset" if score < 60 else "Soft Rain Soundscape",
                    180,
                    ts,
                ),
            )
