"""FastAPI application entrypoint for Serene Mental Wellness."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR
from app.database import init_db
from app.routers import auth, dashboard, journal, moods, profile


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize SQLite schema and upload folders on server boot."""
    init_db()
    yield


app = FastAPI(
    title="Serene Mental Wellness",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Apply baseline security and camera/mic same-origin permission headers."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self)"
    return response

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(moods.router)
app.include_router(journal.router)
app.include_router(dashboard.router)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/sw.js")
def service_worker() -> FileResponse:
    """Serve service worker from root scope for 8 PM local reminders."""
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Return empty 204 for favicon requests to keep server logs clean."""
    return Response(status_code=204)


@app.get("/health")
def health() -> dict[str, str]:
    """Healthcheck endpoint for cloud deployments."""
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    """Serve the Serene SPA."""
    return FileResponse(STATIC_DIR / "index.html")
