"""Download open-source frontend libraries and face-api models into static/."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VENDOR_DIR = BASE_DIR / "static" / "vendor"
MODELS_DIR = BASE_DIR / "static" / "models"

FACE_API_BASE = "https://cdn.jsdelivr.net/npm/@vladmandic/face-api@1.7.15"
CHART_JS_URL = "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"

MANIFESTS = [
    "tiny_face_detector_model-weights_manifest.json",
    "face_expression_model-weights_manifest.json",
    "face_landmark_68_tiny_model-weights_manifest.json",
]


def download_file(url: str, destination: Path) -> None:
    """Download URL to destination path if missing or empty."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "SereneMindAssetFetcher/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    destination.write_bytes(data)
    print(f"Downloaded {destination.relative_to(BASE_DIR)} ({len(data):,} bytes)")


def main() -> None:
    download_file(f"{FACE_API_BASE}/dist/face-api.js", VENDOR_DIR / "face-api.js")
    download_file(CHART_JS_URL, VENDOR_DIR / "chart.umd.min.js")

    for manifest_name in MANIFESTS:
        manifest_path = MODELS_DIR / manifest_name
        download_file(f"{FACE_API_BASE}/model/{manifest_name}", manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for group in manifest:
            for weight_path in group.get("paths", []):
                download_file(
                    f"{FACE_API_BASE}/model/{weight_path}",
                    MODELS_DIR / weight_path,
                )


if __name__ == "__main__":
    main()
