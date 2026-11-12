"""Wellness analytics dashboard aggregations, streaks, and trend insights."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/api", tags=["dashboard"])


def _parse_date(date_str: str) -> datetime.date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()


@router.get("/dashboard")
def get_wellness_dashboard(
    days: int = Query(default=14, ge=1, le=365),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    today: str = Query(default=""),
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    """Compute multi-day mental wellness graphs, mood distributions, streaks, and insights."""
    user_id = str(current_user["id"])
    today_date = _parse_date(today.strip()) if len(today.strip()) == 10 else datetime.now().date()

    if len(start_date.strip()) == 10 and len(end_date.strip()) == 10:
        range_start = _parse_date(start_date.strip())
        range_end = _parse_date(end_date.strip())
        if range_end < range_start:
            range_start, range_end = range_end, range_start
    else:
        range_end = today_date
        range_start = today_date - timedelta(days=days - 1)

    span_days = (range_end - range_start).days + 1
    prev_end = range_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span_days - 1)

    heatmap_start = today_date - timedelta(days=89)

    with get_db() as conn:
        scans = conn.execute(
            """
            SELECT * FROM mood_scans
            WHERE user_id = ? AND local_date >= ? AND local_date <= ?
            ORDER BY local_date ASC, created_at ASC
            """,
            (user_id, min(prev_start, heatmap_start).isoformat(), range_end.isoformat()),
        ).fetchall()

        journals = conn.execute(
            """
            SELECT local_date, mood_tag FROM journal_entries
            WHERE user_id = ? AND local_date >= ? AND local_date <= ?
            """,
            (user_id, min(range_start, heatmap_start).isoformat(), range_end.isoformat()),
        ).fetchall()

        activities = conn.execute(
            """
            SELECT local_date, activity_type, duration_seconds FROM activity_logs
            WHERE user_id = ? AND local_date >= ? AND local_date <= ?
            """,
            (user_id, range_start.isoformat(), range_end.isoformat()),
        ).fetchall()

        all_journal_dates = {
            r["local_date"]
            for r in conn.execute(
                "SELECT DISTINCT local_date FROM journal_entries WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        }
        all_scan_dates = {
            r["local_date"]
            for r in conn.execute(
                "SELECT DISTINCT local_date FROM mood_scans WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        }

    # Partition scans into current window vs previous comparison window
    curr_scans = [s for s in scans if range_start.isoformat() <= s["local_date"] <= range_end.isoformat()]
    prev_scans = [s for s in scans if prev_start.isoformat() <= s["local_date"] <= prev_end.isoformat()]

    daily_scores: dict[str, list[int]] = defaultdict(list)
    daily_moods: dict[str, list[str]] = defaultdict(list)
    tod_scores: dict[str, list[int]] = defaultdict(list)
    mood_counts: Counter[str] = Counter()

    for s in curr_scans:
        daily_scores[s["local_date"]].append(int(s["wellness_score"]))
        daily_moods[s["local_date"]].append(str(s["primary_mood"]))
        tod_scores[str(s["time_of_day"])].append(int(s["wellness_score"]))
        mood_counts[str(s["primary_mood"])] += 1

    journal_counts: Counter[str] = Counter(
        j["local_date"]
        for j in journals
        if range_start.isoformat() <= j["local_date"] <= range_end.isoformat()
    )
    activity_counts: Counter[str] = Counter(a["local_date"] for a in activities)

    # Daily timeline series across the full selected date range
    timeline: list[dict[str, Any]] = []
    for offset in range(span_days):
        d = (range_start + timedelta(days=offset)).isoformat()
        scores = daily_scores.get(d, [])
        avg_score = round(sum(scores) / len(scores)) if scores else None
        dominant = Counter(daily_moods[d]).most_common(1)[0][0] if daily_moods.get(d) else None
        timeline.append(
            {
                "date": d,
                "avg_score": avg_score,
                "scan_count": len(scores),
                "journal_count": journal_counts.get(d, 0),
                "activity_count": activity_counts.get(d, 0),
                "dominant_mood": dominant,
            }
        )

    curr_avg = (
        round(sum(int(s["wellness_score"]) for s in curr_scans) / len(curr_scans))
        if curr_scans
        else None
    )
    prev_avg = (
        round(sum(int(s["wellness_score"]) for s in prev_scans) / len(prev_scans))
        if prev_scans
        else None
    )
    delta = (curr_avg - prev_avg) if (curr_avg is not None and prev_avg is not None) else None

    # Streaks (counting backward from today, allowing today to still be open)
    def calc_streak(dates_set: set[str]) -> int:
        streak = 0
        cursor = today_date
        if cursor.isoformat() not in dates_set:
            cursor = today_date - timedelta(days=1)
        while cursor.isoformat() in dates_set:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    journal_streak = calc_streak(all_journal_dates)
    checkin_streak = calc_streak(all_scan_dates | all_journal_dates)

    # Time-of-day averages
    rhythm = []
    for slot in ("morning", "afternoon", "evening", "night"):
        vals = tod_scores.get(slot, [])
        rhythm.append(
            {
                "slot": slot,
                "avg_score": round(sum(vals) / len(vals)) if vals else None,
                "count": len(vals),
            }
        )

    # Behavioral insights derived strictly from observed user records
    insights: list[str] = []
    journaled_days_scores = [
        int(s["wellness_score"]) for s in curr_scans if journal_counts.get(s["local_date"], 0) > 0
    ]
    non_journaled_scores = [
        int(s["wellness_score"]) for s in curr_scans if journal_counts.get(s["local_date"], 0) == 0
    ]
    if journaled_days_scores and non_journaled_scores:
        j_avg = round(sum(journaled_days_scores) / len(journaled_days_scores))
        nj_avg = round(sum(non_journaled_scores) / len(non_journaled_scores))
        diff = j_avg - nj_avg
        if diff >= 3:
            insights.append(
                f"On days you wrote in your journal, your wellness score averaged {j_avg} vs {nj_avg} on non-journal days (+{diff} pts)."
            )
    valid_rhythm = [r for r in rhythm if r["avg_score"] is not None]
    if len(valid_rhythm) >= 2:
        best_slot = max(valid_rhythm, key=lambda r: r["avg_score"])
        insights.append(
            f"Your calmest emotional window in this period is {best_slot['slot']} (avg {best_slot['avg_score']}/100)."
        )
    if mood_counts:
        top_mood, top_count = mood_counts.most_common(1)[0]
        insights.append(
            f"Your most frequently recorded state was '{top_mood}' ({top_count} check-in{'s' if top_count != 1 else ''})."
        )
    if not insights:
        insights.append("Log a few mood scans and journal entries across days to unlock personal pattern insights.")

    # 90-day heatmap mosaic
    heatmap_scores: dict[str, list[int]] = defaultdict(list)
    for s in scans:
        if s["local_date"] >= heatmap_start.isoformat():
            heatmap_scores[s["local_date"]].append(int(s["wellness_score"]))
    heatmap_journals = Counter(
        j["local_date"] for j in journals if j["local_date"] >= heatmap_start.isoformat()
    )
    heatmap = []
    for offset in range(90):
        d = (heatmap_start + timedelta(days=offset)).isoformat()
        vals = heatmap_scores.get(d, [])
        heatmap.append(
            {
                "date": d,
                "avg_score": round(sum(vals) / len(vals)) if vals else None,
                "checkins": len(vals),
                "journals": heatmap_journals.get(d, 0),
            }
        )

    return {
        "range": {
            "start_date": range_start.isoformat(),
            "end_date": range_end.isoformat(),
            "days": span_days,
        },
        "summary": {
            "avg_score": curr_avg,
            "delta_vs_prev": delta,
            "dominant_mood": mood_counts.most_common(1)[0][0] if mood_counts else None,
            "total_scans": len(curr_scans),
            "total_journals": sum(journal_counts.values()),
            "total_activities": len(activities),
            "journal_streak": journal_streak,
            "checkin_streak": checkin_streak,
        },
        "timeline": timeline,
        "mood_distribution": [
            {"mood": m, "count": c} for m, c in mood_counts.most_common()
        ],
        "time_of_day_rhythm": rhythm,
        "heatmap": heatmap,
        "insights": insights,
    }
