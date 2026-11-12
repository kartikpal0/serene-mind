"""End-to-end API tests for Serene Mental Wellness including email verification & security."""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Create an isolated FastAPI TestClient backed by a temporary SQLite database."""
    monkeypatch.setenv("SERENE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SERENE_DB_PATH", str(tmp_path / "data" / "test_serene.db"))
    monkeypatch.setenv("SERENE_UPLOADS_DIR", str(tmp_path / "data" / "uploads"))
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("SERENE_ENV", raising=False)

    from app import config, main
    from app.security import auth_rate_limiter

    auth_rate_limiter.reset()
    importlib.reload(config)
    importlib.reload(main)
    with TestClient(main.app) as test_client:
        yield test_client


def test_email_verification_rate_limits_and_recovery(client: TestClient) -> None:
    # 1. Register creates an unverified account and does NOT issue a session
    reg = client.post(
        "/api/auth/register",
        json={"email": "maya@example.com", "password": "calm-password-1", "display_name": "Maya"},
    )
    assert reg.status_code == 200
    assert reg.json()["needs_verification"] is True
    assert client.get("/api/auth/me").status_code == 401

    # 2. Unverified login is rejected with 403 + X-Needs-Verification
    unverified_login = client.post(
        "/api/auth/login",
        json={"email": "maya@example.com", "password": "calm-password-1"},
    )
    assert unverified_login.status_code == 403
    assert unverified_login.headers.get("X-Needs-Verification") == "true"

    # 3. Wrong verification codes lock out that code after 5 failed attempts
    for idx in range(5):
        bad_verify = client.post(
            "/api/auth/verify-email",
            json={"email": "maya@example.com", "code": f"00000{idx}"},
        )
        assert bad_verify.status_code == 400
    locked_verify = client.post(
        "/api/auth/verify-email",
        json={"email": "maya@example.com", "code": "000009"},
    )
    assert locked_verify.status_code == 400

    # 4. Resend fresh verification code and verify ownership
    resend = client.post("/api/auth/verify-email/resend", json={"email": "maya@example.com"})
    assert resend.status_code == 200
    outbox = client.get("/api/auth/dev-outbox?email=maya@example.com").json()["messages"]
    verify_code = outbox[0]["otp_or_token"]

    verified = client.post(
        "/api/auth/verify-email",
        json={"email": "maya@example.com", "code": verify_code},
    )
    assert verified.status_code == 200
    assert verified.json()["user"]["email_verified"] is True

    # Verified email cannot be overwritten by another registration
    dup = client.post(
        "/api/auth/register",
        json={"email": "maya@example.com", "password": "other-password-1", "display_name": "Imposter"},
    )
    assert dup.status_code == 409

    # Set a quick PIN via profile
    pin_set = client.patch("/api/profile", json={"quick_pin": "2468", "onboarding_completed": True})
    assert pin_set.status_code == 200
    assert pin_set.json()["user"]["has_pin"] is True
    client.post("/api/auth/logout")

    # 5. PIN brute-force rate limit triggers after 5 failures
    for _ in range(5):
        assert client.post("/api/auth/pin-login", json={"email": "maya@example.com", "pin": "0000"}).status_code == 401
    assert client.post("/api/auth/pin-login", json={"email": "maya@example.com", "pin": "2468"}).status_code == 429

    # 6. Passwordless Email OTP login
    otp_req = client.post("/api/auth/otp/request", json={"email": "otpuser@example.com"})
    assert otp_req.status_code == 200
    otp_outbox = client.get("/api/auth/dev-outbox?email=otpuser@example.com").json()["messages"]
    otp_verify = client.post(
        "/api/auth/otp/verify",
        json={"email": "otpuser@example.com", "code": otp_outbox[0]["otp_or_token"]},
    )
    assert otp_verify.status_code == 200
    assert otp_verify.json()["user"]["email_verified"] is True
    client.post("/api/auth/logout")

    # 7. Forgot password recovery
    rec_req = client.post("/api/auth/recovery/request", json={"email": "maya@example.com"})
    assert rec_req.status_code == 200
    maya_mail = client.get("/api/auth/dev-outbox?email=maya@example.com").json()["messages"]
    reset_token = maya_mail[0]["otp_or_token"]

    reset_res = client.post(
        "/api/auth/recovery/reset",
        json={"token": reset_token, "new_password": "new-serene-password"},
    )
    assert reset_res.status_code == 200
    assert client.post(
        "/api/auth/login",
        json={"email": "maya@example.com", "password": "new-serene-password"},
    ).status_code == 200

    # 8. Account deletion clears user & session
    assert client.delete("/api/profile").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_dev_outbox_disabled_in_cloud_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SERENE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SERENE_DB_PATH", str(tmp_path / "data" / "prod_test.db"))
    monkeypatch.setenv("SERENE_UPLOADS_DIR", str(tmp_path / "data" / "uploads"))
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)

    from app import config, main
    from app.security import auth_rate_limiter

    auth_rate_limiter.reset()
    importlib.reload(config)
    importlib.reload(main)
    with TestClient(main.app) as prod_client:
        providers = prod_client.get("/api/auth/providers").json()
        assert providers["dev_outbox_enabled"] is False
        assert providers["mail_configured"] is False

        # Never leak codes in dev-outbox in production
        outbox = prod_client.get("/api/auth/dev-outbox").json()
        assert outbox["dev_outbox_enabled"] is False
        assert outbox["messages"] == []

        # Registration fails honestly with 503 when no mail provider is configured in production
        reg = prod_client.post(
            "/api/auth/register",
            json={"email": "user@example.com", "password": "strong-password-1"},
        )
        assert reg.status_code == 503


def test_mood_scan_journal_midnight_reset_and_8pm_reminder(client: TestClient) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    guest = client.post("/api/auth/guest", json={"local_date": today})
    assert guest.status_code == 200

    scan = client.post(
        "/api/moods",
        json={
            "local_date": today,
            "time_of_day": "afternoon",
            "primary_mood": "happy",
            "raw_expression": "happy",
            "wellness_score": 89,
            "confidence": 0.92,
            "expressions": {"happy": 0.85, "neutral": 0.15},
            "source": "face_scan",
        },
    )
    assert scan.status_code == 200
    assert scan.json()["bundle"]["mood"] == "happy"

    early_check = client.post(
        "/api/reminders/check",
        json={"local_date": today, "local_time": "19:59"},
    )
    assert early_check.status_code == 200
    assert early_check.json()["should_notify"] is False

    evening_check = client.post(
        "/api/reminders/check",
        json={"local_date": today, "local_time": "20:00"},
    )
    assert evening_check.status_code == 200
    assert evening_check.json()["should_notify"] is True
    assert evening_check.json()["written_today"] is False

    create_entry = client.post(
        "/api/journal",
        data={
            "local_date": today,
            "time_of_day": "evening",
            "mood_tag": "calm",
            "content": "Quiet evening reflection after a walk.",
            "gratitude_note": "Cool evening breeze.",
            "audio_duration": "12",
        },
        files=[
            ("photos", ("sky.png", b"\x89PNG\r\n\x1a\nfake-image-bytes", "image/png")),
            ("audio", ("note.webm", b"OggS-fake-voice-bytes", "audio/webm")),
        ],
    )
    assert create_entry.status_code == 200
    entry = create_entry.json()["entry"]
    assert len(entry["media"]) == 2

    media_resp = client.get(entry["media"][0]["url"])
    assert media_resp.status_code == 200
    assert "no-store" in media_resp.headers.get("cache-control", "")

    after_write = client.post(
        "/api/reminders/check",
        json={"local_date": today, "local_time": "20:15", "force_preview": False},
    )
    assert after_write.status_code == 200
    assert after_write.json()["written_today"] is True
    assert after_write.json()["should_notify"] is False

    tomorrow_journal = client.get(f"/api/journal?local_date={tomorrow}")
    assert tomorrow_journal.status_code == 200
    assert tomorrow_journal.json()["written_today"] is False
    assert tomorrow_journal.json()["count"] == 0

    days_list = client.get("/api/journal/days").json()["days"]
    assert any(d["local_date"] == today for d in days_list)

    dash = client.get(f"/api/dashboard?days=14&today={today}")
    assert dash.status_code == 200
    body = dash.json()
    assert body["summary"]["total_scans"] >= 14
    assert len(body["timeline"]) == 14
    assert len(body["heatmap"]) == 90
