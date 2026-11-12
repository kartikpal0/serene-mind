"""Application configuration loaded from environment variables or defaults."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("SERENE_DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = Path(os.getenv("SERENE_DB_PATH", str(DATA_DIR / "serene.db")))
UPLOADS_DIR = Path(os.getenv("SERENE_UPLOADS_DIR", str(DATA_DIR / "uploads")))
STATIC_DIR = BASE_DIR / "static"


def load_dotenv_file() -> None:
    """Load simple KEY=VALUE entries from .env if present without overriding env."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv_file()


def _clean_secret(val: str) -> str:
    return val.strip().strip('"').strip("'").strip()


def get_settings() -> dict[str, object]:
    """Return runtime configuration settings."""
    resend_key = _clean_secret(os.getenv("RESEND_API_KEY", ""))
    brevo_key = _clean_secret(os.getenv("BREVO_API_KEY", ""))
    smtp_host = _clean_secret(os.getenv("SMTP_HOST", ""))
    mail_configured = bool(resend_key or brevo_key or smtp_host)

    is_cloud_prod = bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or os.getenv("SERENE_ENV", "").strip().lower() == "production"
    )
    dev_outbox_flag = os.getenv("SERENE_DEV_OUTBOX", "auto").strip().lower()
    if dev_outbox_flag in {"1", "true", "yes"}:
        dev_outbox_enabled = not mail_configured
    elif dev_outbox_flag in {"0", "false", "no"}:
        dev_outbox_enabled = False
    else:
        # "auto": enable local dev mail preview only outside cloud production when no mail provider is set
        dev_outbox_enabled = (not mail_configured) and (not is_cloud_prod)

    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    default_base = f"https://{railway_domain}" if railway_domain else "http://127.0.0.1:8000"

    return {
        "base_url": os.getenv("PUBLIC_BASE_URL", default_base).rstrip("/"),
        "is_cloud_prod": is_cloud_prod,
        "mail_configured": mail_configured,
        "dev_outbox_enabled": dev_outbox_enabled,
        "resend_api_key": resend_key,
        "brevo_api_key": brevo_key,
        "email_from": os.getenv(
            "EMAIL_FROM",
            os.getenv("SMTP_FROM", "Serene Wellness <onboarding@resend.dev>"),
        ).strip(),
        "smtp_host": smtp_host,
        "smtp_port": int(os.getenv("SMTP_PORT", "587") or 587),
        "smtp_user": os.getenv("SMTP_USER", "").strip(),
        "smtp_password": os.getenv("SMTP_PASSWORD", "").strip(),
        "smtp_from": os.getenv("SMTP_FROM", "Serene Wellness <noreply@serene.local>").strip(),
        "smtp_use_tls": os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"},
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        "github_client_id": os.getenv("GITHUB_CLIENT_ID", "").strip(),
        "admin_stats_key": _clean_secret(os.getenv("ADMIN_STATS_KEY", "")),
    }
