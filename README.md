# Serene — Quiet Mental Wellness Companion

A minimalistic, calm mental wellness web application for private real-time facial mood sensing, multimedia daily journaling, guided breathing & ambient soundscapes, and multi-day emotional trend tracking.

**Live App:** https://serene-mind-production.up.railway.app

---

## Key Features

### 1. Authentication, Email Verification & Account Recovery
- **Email & Password** with `scrypt` salted password hashing and mandatory **email ownership verification** (6-digit code + clickable `/?verify_token=...` link) before sign-in.
- **Passwordless Email Magic Code (6-digit OTP)** for quick sign-in.
- **Quick PIN** (4–8 digits, configured optionally inside Profile).
- **Guest Demo Explorer** creating an isolated guest space pre-populated with 13 days of historical check-ins, journal entries, and activities.
- **Email Password Recovery** (`Forgot password?`) issuing expiring reset links/tokens and revoking prior sessions on reset.
- **Security Hardening**: Sliding-window rate limiting (`429` on brute-force attempts), max 5 guesses per verification/OTP code, `HttpOnly` / `SameSite=Lax` / HTTPS `Secure` cookies, security headers, and strict gating of the local dev mail outbox in cloud production.

### 2. Low-Friction Profile & Onboarding
- Optional, skippable 15-second onboarding (display name, calm tint, focus chips, feedback style, 8:00 PM reminder toggle).
- Editable anytime via Profile: avatar photo upload, pronouns, age range, personal intention, **Light Linen / Evening Sage** theme toggle, **JSON data export**, and permanent **Delete Account**.

### 3. On-Device Real-Time Facial Mood Scanning
- Powered locally in the browser by [`@vladmandic/face-api`](https://github.com/vladmandic/face-api) (`tinyFaceDetector`, `faceLandmark68TinyNet`, `faceExpressionNet`) with all weights bundled under `static/models/`.
- **100% client-side inference** — webcam video frames never leave the user's device.
- Smooths expression probabilities, displays live emotional bars (`Happy`, `Calm`, `Sad`, `Anxious`, `Tense`, `Alert`), computes a 0–100 wellness score, offers an **8-second Guided Scan**, and includes one-tap **manual mood check-ins** when a camera isn't used.

### 4. Mood-Tailored Care, Breathing, Soundscapes & Playlists
- **Guided Breathing Pacer**: `4-7-8 Calm Reset`, `Box Breathing (4-4-4-4)`, `Coherent 5-5`, and `Physiological Sigh` with gentle chime cues.
- **Built-in Ambient Sound Mixer**: Synthesized in real time via the Web Audio API (`Soft Rain`, `Warm Breeze`, `Warm Pink Noise`, `432Hz Singing Bowl`) with individual volume sliders.
- **Curated Suggestions & Playlists**: Empathetic reflections, micro-activities, and Spotify / YouTube Music playlist links tailored to your detected mood.

### 5. Daily Digital Journal, Midnight Reset & 8 PM Reminder
- Log text reflections, rotating prompts, gratitude notes, multiple photos, and live microphone **voice recordings** (`MediaRecorder` + real-time waveform canvas + audio playback) at any time of day.
- **Midnight Reset**: Today's journal canvas clears cleanly at `00:00` local time for a fresh start while preserving every past entry in the **Archive** tab.
- **8:00 PM Reminder**: Checks whether you have journaled today; if not, triggers an in-app banner, browser/Service Worker notification (`static/sw.js`), and optional reminder email (includes a **Preview 8 PM Reminder** button for instant testing).

### 6. Wellness Tracker Dashboard
- Inspect wellbeing over `7D`, `14D`, `30D`, `90D`, or a custom date range using `Chart.js`:
  - **Mental Wellness Trajectory** (area/line chart with journaled-day markers)
  - **Emotional Spectrum** (mood distribution doughnut)
  - **Time-of-Day Rhythm** (`morning`, `afternoon`, `evening`, `night` averages)
  - **90-Day Wellness Mosaic** (clickable heatmap linking straight to archived days)
  - **Active Streaks & Personal Pattern Insights**

---

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, Uvicorn, SQLite (`sqlite3`)
- **Frontend:** Vanilla ES Modules, CSS custom properties, Service Worker (`sw.js`)
- **Client Libraries (vendored locally in `static/vendor/`):** `@vladmandic/face-api`, `Chart.js`
- **Email Delivery:** Resend HTTPS API, Brevo HTTPS API, or SMTP (plus gated local dev outbox preview for offline testing)

---

## Project Structure

```text
serene-mind/
├── app/
│   ├── main.py                # FastAPI entrypoint, security headers, /health, SPA serving
│   ├── config.py              # Environment & mail/storage configuration
│   ├── database.py            # SQLite schema initialization & safe migrations
│   ├── deps.py                # Session auth dependencies & HTTPS cookie helpers
│   ├── mail_service.py        # Resend API, Brevo API, SMTP & local dev outbox
│   ├── security.py            # scrypt hashing, SHA-256 tokens, rate limiter
│   ├── seed.py                # 13-day demo guest history seeder
│   ├── wellness_catalog.py    # Mood reflections, prompts, activities & playlists
│   └── routers/
│       ├── auth.py            # Register, email verify, login, OTP, PIN, guest, recovery
│       ├── profile.py         # Profile updates, avatar upload, JSON export, account delete
│       ├── moods.py           # Mood check-ins, catalog & activity logging
│       ├── journal.py         # Multimedia journal, private media serving, 8 PM check
│       └── dashboard.py       # Multi-day analytics, streaks, heatmap & insights
├── static/
│   ├── index.html             # Single-page calm UI
│   ├── sw.js                  # Service worker for 8 PM reminder notifications
│   ├── css/styles.css         # Light Linen & Evening Sage themes
│   ├── js/                    # api.js, app.js, audio.js, dashboard.js, faceScan.js, journal.js
│   ├── vendor/                # Bundled face-api.js & chart.umd.min.js
│   └── models/                # Bundled face-api detector, landmark & expression weights
├── scripts/
│   └── fetch_vendor_assets.py # Script to refresh local vendor JS and ML model weights
├── tests/
│   └── test_serene_api.py     # End-to-end API, auth, security & reminder test suite
├── Dockerfile
├── pyproject.toml
├── railway.json
└── requirements.txt
```

---

## Local Setup

1. **Install dependencies** (using [`uv`](https://docs.astral.sh/uv/)):
   ```powershell
   uv sync --extra dev
   ```
2. **Optional environment config:**
   Copy `.env.example` to `.env` and fill in any mail provider credentials if testing real email delivery locally. When running locally without `RESEND_API_KEY`, `BREVO_API_KEY`, or `SMTP_HOST`, verification codes and reset links appear in the **Local Mail Outbox** on the login page.
3. **Run the server:**
   ```powershell
   uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
   Open `http://127.0.0.1:8000`.
4. **Run tests:**
   ```powershell
   uv run pytest -v
   ```

---

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `SERENE_DATA_DIR` | Directory for `serene.db` and `uploads/` | `./data` (`/data` in Docker) |
| `RESEND_API_KEY` | Resend HTTPS API key for verification & recovery emails | `""` |
| `BREVO_API_KEY` | Brevo HTTPS API key for verification & recovery emails | `""` |
| `EMAIL_FROM` | Sender header (`Name <email@domain>`) for Resend / Brevo | `Serene Wellness <onboarding@resend.dev>` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_USE_TLS` | Optional SMTP fallback | `""` (`587`, TLS `true`) |
| `PUBLIC_BASE_URL` | Base URL used in verification & password reset links | Request origin / `http://127.0.0.1:8000` |
| `SERENE_DEV_OUTBOX` | `auto`, `true`, or `false` (auto-disabled in cloud production) | `auto` |

---

## Deploying to Railway

1. Attach a persistent volume mounted at `/data` and set `SERENE_DATA_DIR=/data`.
2. Add your email provider key (`RESEND_API_KEY` or `BREVO_API_KEY` + `EMAIL_FROM`, or `SMTP_*`) in Railway Variables.
3. Deploy using the included `Dockerfile` and `railway.json` (`railway up --detach`).

---

## Privacy & Wellness Notice

- Facial expression analysis runs locally inside your browser; video frames are never uploaded or stored.
- Uploaded journal photos, voice notes, and avatars are served only to the authenticated owner with `Cache-Control: private, no-store`.
- Serene is a personal reflection and wellbeing tool and does not replace professional clinical or crisis care. Built-in crisis helpline links (`988`, `Tele-MANAS 14416`, `NHS 111`, `findahelpline.com`) are accessible from the app footer.
