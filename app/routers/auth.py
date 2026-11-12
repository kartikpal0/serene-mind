"""Authentication endpoints with email ownership verification, rate limiting, and recovery."""

from __future__ import annotations

import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.config import get_settings
from app.database import get_db
from app.deps import (
    clear_session_cookie,
    extract_session_token,
    get_current_user,
    serialize_user,
    set_session_cookie,
)
from app.mail_service import send_email_message
from app.security import (
    AUTH_CODE_TTL_MINUTES,
    MAX_CODE_ATTEMPTS,
    SESSION_COOKIE_NAME,
    auth_rate_limiter,
    generate_numeric_otp,
    generate_session_token,
    hash_secret,
    hash_token,
    utc_now,
    utc_now_iso,
    verify_secret,
)
from app.seed import seed_guest_history

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=60)


class VerifyEmailRequest(BaseModel):
    email: str = Field(default="", max_length=254)
    code: str = Field(default="", max_length=16)
    token: str = Field(default="", max_length=256)


class ResendVerificationRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


class OtpRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)


class OtpVerifyRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    code: str = Field(..., min_length=4, max_length=12)
    display_name: str = Field(default="", max_length=60)


class PinLoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    pin: str = Field(..., min_length=4, max_length=8)


class GuestLoginRequest(BaseModel):
    local_date: str = Field(default="")


class RecoveryRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)


class RecoveryResetRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=128)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def _normalize_email(email: str) -> str:
    cleaned = email.strip().lower()
    if not EMAIL_REGEX.match(cleaned):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    return cleaned


def _resolve_base_url(request: Request) -> str:
    settings = get_settings()
    env_base = str(settings["base_url"])
    req_base = str(request.base_url).rstrip("/")
    if env_base == "http://127.0.0.1:8000" and req_base and not req_base.startswith("http://testserver"):
        return req_base
    return env_base


def _create_session_for_user(
    conn: sqlite3.Connection,
    response: Response,
    request: Request,
    user_id: str,
    auth_method: str,
) -> str:
    raw_token, token_hash, expires_at = generate_session_token()
    conn.execute(
        """
        INSERT INTO sessions (token_hash, user_id, auth_method, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (token_hash, user_id, auth_method, expires_at, utc_now_iso()),
    )
    set_session_cookie(response, raw_token, request=request)
    return raw_token


def _issue_email_verification(
    conn: sqlite3.Connection,
    *,
    email: str,
    display_name: str,
    base_url: str,
) -> dict[str, str]:
    code = generate_numeric_otp(6)
    link_token = secrets.token_urlsafe(24)
    expires_at = (utc_now() + timedelta(minutes=AUTH_CODE_TTL_MINUTES)).isoformat()

    conn.execute(
        "UPDATE auth_codes SET used = 1 WHERE email = ? AND purpose = 'verify_email' AND used = 0",
        (email,),
    )
    conn.execute(
        """
        INSERT INTO auth_codes (id, email, purpose, code_hash, link_token_hash, expires_at, created_at)
        VALUES (?, ?, 'verify_email', ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            email,
            hash_token(code),
            hash_token(link_token),
            expires_at,
            utc_now_iso(),
        ),
    )
    verify_url = f"{base_url}/?verify_token={link_token}"
    return send_email_message(
        conn,
        recipient=email,
        subject="Verify your Serene email address",
        body_text=(
            f"Hi {display_name},\n\n"
            f"Welcome to Serene. Confirm that this email belongs to you using either:\n\n"
            f"Verification code: {code}\n"
            f"Or click this link: {verify_url}\n\n"
            f"This code expires in {AUTH_CODE_TTL_MINUTES} minutes."
        ),
        action_url=verify_url,
        otp_or_token=code,
        required_for_auth=True,
    )


@router.get("/providers")
def auth_providers() -> dict[str, object]:
    """Report mail delivery status and supported authentication methods."""
    settings = get_settings()
    return {
        "mail_configured": bool(settings["mail_configured"]),
        "dev_outbox_enabled": bool(settings["dev_outbox_enabled"]),
        "is_cloud_prod": bool(settings["is_cloud_prod"]),
        "google_oauth_configured": bool(settings["google_client_id"]),
        "github_oauth_configured": bool(settings["github_client_id"]),
        "methods": ["password", "email_otp", "pin", "guest"],
    }


@router.post("/register")
def register(payload: RegisterRequest, request: Request) -> dict[str, object]:
    """Create a pending account and require email verification before signing in."""
    email = _normalize_email(payload.email)
    ip = _client_ip(request)
    auth_rate_limiter.check(f"register:{ip}", limit=10, window_seconds=600)

    display_name = payload.display_name.strip() or email.split("@", 1)[0].replace(".", " ").title()
    now = utc_now_iso()
    base_url = _resolve_base_url(request)

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id, email_verified FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if existing and int(existing["email_verified"]) == 1:
            raise HTTPException(status_code=409, detail="An account with this email already exists.")

        if existing:
            conn.execute(
                """
                UPDATE users
                SET password_hash = ?, display_name = ?, created_at = ?
                WHERE id = ?
                """,
                (hash_secret(payload.password), display_name, now, existing["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO users (id, email, password_hash, email_verified, display_name, created_at)
                VALUES (?, ?, ?, 0, ?, ?)
                """,
                (str(uuid.uuid4()), email, hash_secret(payload.password), display_name, now),
            )

        mail_meta = _issue_email_verification(
            conn,
            email=email,
            display_name=display_name,
            base_url=base_url,
        )

    return {
        "needs_verification": True,
        "email": email,
        "delivery_mode": mail_meta["delivery_mode"],
        "message": "Check your inbox for a 6-digit verification code or link to activate your account.",
    }


@router.post("/verify-email")
def verify_email(
    payload: VerifyEmailRequest,
    response: Response,
    request: Request,
) -> dict[str, object]:
    """Verify email ownership using a 6-digit code or verification link token."""
    ip = _client_ip(request)
    auth_rate_limiter.check(f"verify_email:{ip}", limit=15, window_seconds=300)
    now = utc_now()

    with get_db() as conn:
        if payload.token.strip():
            token_hash = hash_token(payload.token.strip())
            code_row = conn.execute(
                """
                SELECT * FROM auth_codes
                WHERE purpose = 'verify_email' AND link_token_hash = ? AND used = 0
                ORDER BY created_at DESC LIMIT 1
                """,
                (token_hash,),
            ).fetchone()
            if not code_row or datetime.fromisoformat(code_row["expires_at"]) < now:
                raise HTTPException(status_code=400, detail="Verification link is invalid or expired.")
            target_email = str(code_row["email"])
        else:
            target_email = _normalize_email(payload.email)
            submitted_hash = hash_token(payload.code.strip())
            code_row = conn.execute(
                """
                SELECT * FROM auth_codes
                WHERE email = ? AND purpose = 'verify_email' AND used = 0
                ORDER BY created_at DESC LIMIT 1
                """,
                (target_email,),
            ).fetchone()
            if not code_row or datetime.fromisoformat(code_row["expires_at"]) < now:
                raise HTTPException(status_code=400, detail="Verification code is invalid or expired.")

            if int(code_row["attempts"]) >= MAX_CODE_ATTEMPTS:
                conn.execute("UPDATE auth_codes SET used = 1 WHERE id = ?", (code_row["id"],))
                raise HTTPException(
                    status_code=429,
                    detail="Too many wrong codes. Please request a new verification code.",
                )

            if code_row["code_hash"] != submitted_hash:
                new_attempts = int(code_row["attempts"]) + 1
                conn.execute(
                    "UPDATE auth_codes SET attempts = ?, used = ? WHERE id = ?",
                    (new_attempts, 1 if new_attempts >= MAX_CODE_ATTEMPTS else 0, code_row["id"]),
                )
                raise HTTPException(status_code=400, detail="Verification code does not match.")

        conn.execute("UPDATE auth_codes SET used = 1 WHERE id = ?", (code_row["id"],))
        conn.execute("UPDATE users SET email_verified = 1 WHERE email = ?", (target_email,))
        user_row = conn.execute("SELECT * FROM users WHERE email = ?", (target_email,)).fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="Account not found.")

        _create_session_for_user(conn, response, request, user_row["id"], "password")
        return {"user": serialize_user(user_row), "message": "Email verified."}


@router.post("/verify-email/resend")
def resend_verification(payload: ResendVerificationRequest, request: Request) -> dict[str, object]:
    """Resend an email verification code if an unverified account exists."""
    email = _normalize_email(payload.email)
    ip = _client_ip(request)
    auth_rate_limiter.check(f"resend_verify:{ip}:{email}", limit=4, window_seconds=300)
    base_url = _resolve_base_url(request)
    delivery_mode = "none"

    with get_db() as conn:
        user_row = conn.execute(
            "SELECT display_name, email_verified FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if user_row and int(user_row["email_verified"]) == 0:
            mail_meta = _issue_email_verification(
                conn,
                email=email,
                display_name=str(user_row["display_name"]),
                base_url=base_url,
            )
            delivery_mode = mail_meta["delivery_mode"]

    return {
        "message": "If an unverified account matches that email, a fresh verification code has been sent.",
        "delivery_mode": delivery_mode,
    }


@router.post("/login")
def login(payload: LoginRequest, response: Response, request: Request) -> dict[str, object]:
    """Sign in using verified email and password."""
    email = _normalize_email(payload.email)
    ip = _client_ip(request)
    auth_rate_limiter.check(f"login:{ip}:{email}", limit=10, window_seconds=300)

    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not verify_secret(payload.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        if int(row["email_verified"]) == 0 and int(row["is_guest"]) == 0:
            raise HTTPException(
                status_code=403,
                detail="Please verify your email address before signing in.",
                headers={"X-Needs-Verification": "true"},
            )

        _create_session_for_user(conn, response, request, row["id"], "password")
        return {"user": serialize_user(row)}


@router.post("/pin-login")
def pin_login(payload: PinLoginRequest, response: Response, request: Request) -> dict[str, object]:
    """Sign in quickly with verified email and a quick PIN configured in Profile."""
    email = _normalize_email(payload.email)
    ip = _client_ip(request)
    # Strict rate limit to prevent 4-digit PIN brute forcing
    auth_rate_limiter.check(f"pin:{ip}:{email}", limit=5, window_seconds=900)

    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not row["pin_hash"] or not verify_secret(payload.pin.strip(), row["pin_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or quick PIN.")
        if int(row["email_verified"]) == 0 and int(row["is_guest"]) == 0:
            raise HTTPException(
                status_code=403,
                detail="Please verify your email address before signing in.",
                headers={"X-Needs-Verification": "true"},
            )

        _create_session_for_user(conn, response, request, row["id"], "pin")
        return {"user": serialize_user(row)}


@router.post("/otp/request")
def request_login_otp(payload: OtpRequest, request: Request) -> dict[str, object]:
    """Send a 6-digit passwordless login code via email."""
    email = _normalize_email(payload.email)
    ip = _client_ip(request)
    auth_rate_limiter.check(f"otp_req:{ip}:{email}", limit=5, window_seconds=300)

    code = generate_numeric_otp(6)
    expires_at = (utc_now() + timedelta(minutes=AUTH_CODE_TTL_MINUTES)).isoformat()

    with get_db() as conn:
        conn.execute(
            "UPDATE auth_codes SET used = 1 WHERE email = ? AND purpose = 'login_otp' AND used = 0",
            (email,),
        )
        conn.execute(
            """
            INSERT INTO auth_codes (id, email, purpose, code_hash, expires_at, created_at)
            VALUES (?, ?, 'login_otp', ?, ?, ?)
            """,
            (str(uuid.uuid4()), email, hash_token(code), expires_at, utc_now_iso()),
        )
        mail_meta = send_email_message(
            conn,
            recipient=email,
            subject="Your Serene sign-in code",
            body_text=(
                f"Use this 6-digit code to sign in to Serene:\n\n"
                f"  {code}\n\n"
                f"This code expires in {AUTH_CODE_TTL_MINUTES} minutes."
            ),
            otp_or_token=code,
            required_for_auth=True,
        )

    return {
        "message": "A 6-digit sign-in code has been sent to your email.",
        "delivery_mode": mail_meta["delivery_mode"],
    }


@router.post("/otp/verify")
def verify_login_otp(
    payload: OtpVerifyRequest,
    response: Response,
    request: Request,
) -> dict[str, object]:
    """Verify a 6-digit email login code, marking the email verified and signing in."""
    email = _normalize_email(payload.email)
    ip = _client_ip(request)
    auth_rate_limiter.check(f"otp_verify:{ip}:{email}", limit=10, window_seconds=300)

    submitted_hash = hash_token(payload.code.strip())
    now = utc_now()

    with get_db() as conn:
        code_row = conn.execute(
            """
            SELECT * FROM auth_codes
            WHERE email = ? AND purpose = 'login_otp' AND used = 0
            ORDER BY created_at DESC LIMIT 1
            """,
            (email,),
        ).fetchone()
        if not code_row or datetime.fromisoformat(code_row["expires_at"]) < now:
            raise HTTPException(status_code=401, detail="Invalid or expired sign-in code.")

        if int(code_row["attempts"]) >= MAX_CODE_ATTEMPTS:
            conn.execute("UPDATE auth_codes SET used = 1 WHERE id = ?", (code_row["id"],))
            raise HTTPException(status_code=429, detail="Too many wrong attempts. Request a new code.")

        if code_row["code_hash"] != submitted_hash:
            new_attempts = int(code_row["attempts"]) + 1
            conn.execute(
                "UPDATE auth_codes SET attempts = ?, used = ? WHERE id = ?",
                (new_attempts, 1 if new_attempts >= MAX_CODE_ATTEMPTS else 0, code_row["id"]),
            )
            raise HTTPException(status_code=401, detail="Invalid sign-in code.")

        conn.execute("UPDATE auth_codes SET used = 1 WHERE id = ?", (code_row["id"],))

        user_row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user_row:
            user_id = str(uuid.uuid4())
            display_name = payload.display_name.strip() or email.split("@", 1)[0].replace(".", " ").title()
            conn.execute(
                """
                INSERT INTO users (id, email, password_hash, email_verified, display_name, created_at)
                VALUES (?, ?, NULL, 1, ?, ?)
                """,
                (user_id, email, display_name, utc_now_iso()),
            )
            user_row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        elif int(user_row["email_verified"]) == 0:
            conn.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user_row["id"],))
            user_row = conn.execute("SELECT * FROM users WHERE id = ?", (user_row["id"],)).fetchone()

        _create_session_for_user(conn, response, request, user_row["id"], "email_otp")
        return {"user": serialize_user(user_row)}


@router.post("/guest")
def guest_login(
    payload: GuestLoginRequest,
    response: Response,
    request: Request,
) -> dict[str, object]:
    """Create a demo guest sanctuary pre-seeded with 13 days of wellness history."""
    ip = _client_ip(request)
    auth_rate_limiter.check(f"guest:{ip}", limit=12, window_seconds=300)

    local_date = payload.local_date.strip() or datetime.now().strftime("%Y-%m-%d")
    user_id = str(uuid.uuid4())
    short_id = user_id[:6]
    email = f"guest-{short_id}@serene.local"
    now = utc_now_iso()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO users (
                id, email, password_hash, email_verified, display_name, avatar_tint,
                focus_goals_json, intention, onboarding_completed, is_guest, created_at
            ) VALUES (?, ?, NULL, 0, ?, 'sage', '["Manage Stress", "Daily Reflection"]',
                'Taking a few quiet minutes for myself each day.', 1, 1, ?)
            """,
            (user_id, email, "Guest Explorer", now),
        )
        seed_guest_history(conn, user_id, local_date)
        _create_session_for_user(conn, response, request, user_id, "guest")
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    return {"user": serialize_user(row)}


@router.post("/recovery/request")
def request_password_recovery(payload: RecoveryRequest, request: Request) -> dict[str, object]:
    """Send a password reset link and token to the user's email if a non-guest account exists."""
    email = _normalize_email(payload.email)
    ip = _client_ip(request)
    auth_rate_limiter.check(f"recovery_req:{ip}:{email}", limit=5, window_seconds=300)

    settings = get_settings()
    base_url = _resolve_base_url(request)
    delivery_mode = "none"

    with get_db() as conn:
        user_row = conn.execute(
            "SELECT id, display_name, is_guest FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if user_row and int(user_row["is_guest"]) == 0:
            raw_token = secrets.token_urlsafe(24)
            expires_at = (utc_now() + timedelta(minutes=AUTH_CODE_TTL_MINUTES)).isoformat()
            conn.execute(
                "UPDATE auth_codes SET used = 1 WHERE email = ? AND purpose = 'password_reset' AND used = 0",
                (email,),
            )
            conn.execute(
                """
                INSERT INTO auth_codes (id, email, purpose, code_hash, expires_at, created_at)
                VALUES (?, ?, 'password_reset', ?, ?, ?)
                """,
                (str(uuid.uuid4()), email, hash_token(raw_token), expires_at, utc_now_iso()),
            )
            reset_url = f"{base_url}/?reset_token={raw_token}"
            mail_meta = send_email_message(
                conn,
                recipient=email,
                subject="Reset your Serene password",
                body_text=(
                    f"Hi {user_row['display_name']},\n\n"
                    f"We received a request to reset your Serene password.\n"
                    f"Open this link or paste the recovery token below:\n\n"
                    f"Link: {reset_url}\n"
                    f"Token: {raw_token}\n\n"
                    f"This link expires in {AUTH_CODE_TTL_MINUTES} minutes."
                ),
                action_url=reset_url,
                otp_or_token=raw_token,
                required_for_auth=True,
            )
            delivery_mode = mail_meta["delivery_mode"]
        elif not settings["mail_configured"] and not settings["dev_outbox_enabled"]:
            raise HTTPException(
                status_code=503,
                detail="Email recovery is unavailable until a mail provider is configured on the server.",
            )

    return {
        "message": "If an account matches that email, recovery instructions have been sent.",
        "delivery_mode": delivery_mode,
    }


@router.post("/recovery/reset")
def reset_password(
    payload: RecoveryResetRequest,
    response: Response,
    request: Request,
) -> dict[str, object]:
    """Reset a user's password using a valid recovery token, mark verified, and sign in."""
    ip = _client_ip(request)
    auth_rate_limiter.check(f"recovery_reset:{ip}", limit=10, window_seconds=300)

    token_hash = hash_token(payload.token.strip())
    now = utc_now()

    with get_db() as conn:
        code_row = conn.execute(
            """
            SELECT * FROM auth_codes
            WHERE purpose = 'password_reset' AND code_hash = ? AND used = 0
            ORDER BY created_at DESC LIMIT 1
            """,
            (token_hash,),
        ).fetchone()
        if not code_row or datetime.fromisoformat(code_row["expires_at"]) < now:
            raise HTTPException(status_code=400, detail="Recovery token is invalid or expired.")

        user_row = conn.execute("SELECT * FROM users WHERE email = ?", (code_row["email"],)).fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="Account not found.")

        conn.execute("UPDATE auth_codes SET used = 1 WHERE id = ?", (code_row["id"],))
        conn.execute(
            "UPDATE users SET password_hash = ?, email_verified = 1 WHERE id = ?",
            (hash_secret(payload.new_password), user_row["id"]),
        )
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_row["id"],))
        _create_session_for_user(conn, response, request, user_row["id"], "password")
        updated_user = conn.execute("SELECT * FROM users WHERE id = ?", (user_row["id"],)).fetchone()

    return {"user": serialize_user(updated_user), "message": "Password updated successfully."}


@router.get("/dev-outbox")
def list_dev_outbox(email: str = Query(default="")) -> dict[str, object]:
    """Return local dev email previews ONLY when dev_outbox_enabled is true."""
    settings = get_settings()
    if not settings["dev_outbox_enabled"]:
        return {
            "mail_configured": bool(settings["mail_configured"]),
            "dev_outbox_enabled": False,
            "messages": [],
        }

    with get_db() as conn:
        if email.strip():
            rows = conn.execute(
                """
                SELECT id, recipient, subject, body_text, action_url, otp_or_token, delivery_mode, created_at
                FROM dev_outbox
                WHERE recipient = ?
                ORDER BY created_at DESC LIMIT 10
                """,
                (email.strip().lower(),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, recipient, subject, body_text, action_url, otp_or_token, delivery_mode, created_at
                FROM dev_outbox
                ORDER BY created_at DESC LIMIT 10
                """
            ).fetchall()

    return {
        "mail_configured": bool(settings["mail_configured"]),
        "dev_outbox_enabled": True,
        "messages": [dict(row) for row in rows],
    }


@router.get("/me")
def me(current_user: dict[str, object] = Depends(get_current_user)) -> dict[str, object]:
    """Return the authenticated user's profile."""
    return {"user": current_user}


@router.post("/logout")
def logout(
    response: Response,
    request: Request,
    cookie_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    """Sign out and revoke the active session token."""
    raw_token = extract_session_token(cookie_token, authorization)
    if raw_token:
        with get_db() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(raw_token),))
    clear_session_cookie(response, request=request)
    return {"message": "Signed out gently."}
