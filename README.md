# Serene — Quiet Mental Wellness Companion

A minimalistic, calm mental wellness web application built with **FastAPI**, **SQLite**, **Chart.js**, **Web Audio API**, and **`@vladmandic/face-api`** (all ML models and frontend scripts bundled locally under `static/`).

## Features
- **Multi-Method Authentication & Email Recovery**: Email + Password, 6-digit Email Magic Code (OTP), Quick PIN, and Guest Demo Space (seeded with 14-day wellness history). Includes Forgot Password recovery tokens/links via SMTP or the built-in Local Dev Mail Outbox preview.
- **Effortless Profile & Onboarding**: Optional 15-second skippable onboarding (name, calm tint, focus chips, feedback tone, evening reminder) plus profile photo upload, theme switch (Light Linen / Evening Sage), and full JSON data export.
- **On-Device Real-Time Facial Mood Scan**: Uses `@vladmandic/face-api` (`tinyFaceDetector`, `faceLandmark68TinyNet`, `faceExpressionNet`) entirely inside the browser—zero video frames leave your device—plus manual mood check-in fallback.
- **Mood-Tailored Care, Breathing, Soundscapes & Playlists**: Interactive breathing pacer (`4-7-8`, `Box`, `Coherent 5-5`, `Physiological Sigh`), real-time Web Audio ambient sound mixer (`Soft Rain`, `Warm Breeze`, `Pink Noise`, `432Hz Singing Bowl`), and mood-matched Spotify/YouTube Music playlists.
- **Daily Multimedia Journal**: Add text, gratitude notes, multiple photos, and live microphone voice recordings (`MediaRecorder` + waveform) anytime throughout the day.
- **Midnight Reset & 8:00 PM Reminder**: Today's journal canvas resets cleanly at midnight while preserving all previous days in **Archive**. At 8:00 PM (if today's journal is empty), triggers a browser/Service Worker notification, in-app banner, and optional reminder email.
- **Wellness Tracker Dashboard**: 7D / 14D / 30D / 90D / Custom date range views with Wellness Trajectory chart, Emotional Spectrum chart, Time-of-Day Rhythm, 90-day clickable mosaic heatmap, streaks, and computed pattern insights.

## Running Locally
```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Then open `http://127.0.0.1:8000` in your browser.

### Optional Real Email / SMTP
Copy `.env.example` to `.env` and fill in `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, and `SMTP_PASSWORD`. When `SMTP_HOST` is blank, recovery links and OTP codes are safely shown in the **Local Mail Outbox** on the login page for testing.
