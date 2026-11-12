"""Email delivery service supporting Resend API, Brevo API, SMTP, and gated local dev outbox."""

from __future__ import annotations

import json
import smtplib
import sqlite3
import urllib.error
import urllib.request
import uuid
from email.message import EmailMessage

from fastapi import HTTPException

from app.config import get_settings
from app.security import utc_now_iso


def _send_via_resend(api_key: str, sender: str, recipient: str, subject: str, body_text: str) -> None:
    payload = json.dumps(
        {
            "from": sender,
            "to": [recipient],
            "subject": subject,
            "text": body_text,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "SereneWellness/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"Resend returned HTTP {resp.status}")


def _send_via_brevo(api_key: str, sender: str, recipient: str, subject: str, body_text: str) -> None:
    sender_email = sender
    sender_name = "Serene Wellness"
    if "<" in sender and ">" in sender:
        name_part, email_part = sender.split("<", 1)
        sender_name = name_part.strip() or sender_name
        sender_email = email_part.rstrip(">").strip()

    payload = json.dumps(
        {
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": recipient}],
            "subject": subject,
            "textContent": body_text,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "User-Agent": "SereneWellness/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"Brevo returned HTTP {resp.status}")


def _send_via_smtp(settings: dict[str, object], recipient: str, subject: str, body_text: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = str(settings["smtp_from"])
    msg["To"] = recipient
    msg.set_content(body_text)
    with smtplib.SMTP(str(settings["smtp_host"]), int(settings["smtp_port"]), timeout=12) as server:
        if settings["smtp_use_tls"]:
            server.starttls()
        if settings["smtp_user"] and settings["smtp_password"]:
            server.login(str(settings["smtp_user"]), str(settings["smtp_password"]))
        server.send_message(msg)


def send_email_message(
    conn: sqlite3.Connection,
    *,
    recipient: str,
    subject: str,
    body_text: str,
    action_url: str = "",
    otp_or_token: str = "",
    required_for_auth: bool = False,
) -> dict[str, str]:
    """Send an email through a real provider when configured, or dev_outbox only in local dev."""
    settings = get_settings()
    resend_key = str(settings["resend_api_key"])
    brevo_key = str(settings["brevo_api_key"])
    smtp_host = str(settings["smtp_host"])
    email_from = str(settings["email_from"])
    dev_outbox_enabled = bool(settings["dev_outbox_enabled"])

    delivery_mode = ""
    last_error = ""

    if resend_key:
        try:
            _send_via_resend(resend_key, email_from, recipient, subject, body_text)
            delivery_mode = "resend"
        except Exception as exc:
            last_error = str(exc)
    elif brevo_key:
        try:
            _send_via_brevo(brevo_key, email_from, recipient, subject, body_text)
            delivery_mode = "brevo"
        except Exception as exc:
            last_error = str(exc)
    elif smtp_host:
        try:
            _send_via_smtp(settings, recipient, subject, body_text)
            delivery_mode = "smtp"
        except Exception as exc:
            last_error = str(exc)

    if delivery_mode:
        return {"id": str(uuid.uuid4()), "delivery_mode": delivery_mode}

    # No real mail provider succeeded
    if not dev_outbox_enabled:
        if required_for_auth:
            detail = (
                f"Email delivery failed ({last_error})."
                if last_error
                else "Email verification is not active because no mail provider (RESEND_API_KEY, BREVO_API_KEY, or SMTP_HOST) is configured yet."
            )
            raise HTTPException(status_code=503, detail=detail)
        return {"id": "", "delivery_mode": "disabled"}

    # Local development preview only (never reachable when dev_outbox_enabled is False)
    mail_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO dev_outbox (id, recipient, subject, body_text, action_url, otp_or_token, delivery_mode, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'local_dev_preview', ?)
        """,
        (
            mail_id,
            recipient.lower(),
            subject,
            body_text,
            action_url,
            otp_or_token,
            utc_now_iso(),
        ),
    )
    return {"id": mail_id, "delivery_mode": "local_dev_preview"}
