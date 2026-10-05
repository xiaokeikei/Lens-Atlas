"""Serve an isolated synthetic NAS for authorized Android integration checks.

Never connects to a real NAS or indexes any user album. All files live in .runtime.
"""
from pathlib import Path
import hashlib
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
import uvicorn
from backend.app import create_app
from backend.config import Config


def main():
    staging = ROOT / ".runtime" / "android-nas-validation"
    staging.mkdir(parents=True, exist_ok=True)
    session = Path(tempfile.mkdtemp(prefix="fixture-", dir=staging))
    media = session / "synthetic-media"
    media.mkdir()
    for i in (1, 2):
        image = Image.new("RGB", (320, 240), "#257b64")
        ImageDraw.Draw(image).text((15, 100), f"SYNTHETIC FIXTURE {i} - NOT A REAL PHOTO", fill="white")
        exif = Image.Exif()
        exif[272] = "SYNTHETIC Android NAS Camera"
        image.save(media / f"SYNTHETIC-{i}.jpg", exif=exif)
    def hashes():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in media.iterdir()}
    original = hashes()
    config = Config(data_dir=session / "app-data", desktop=False, allowed_roots=[media])
    app = create_app(config, start_scanner=False)
    with TestClient(app) as client:
        setup_code = (session / "app-data" / "setup-code.txt").read_text().strip()
        result = client.post("/api/auth/setup", json={"password": "AndroidFixture123!", "setup_code": setup_code})
        assert result.status_code == 200, result.text
        token = client.post("/api/auth/login", json={"password": "AndroidFixture123!"}).json()["token"]
        client.headers["Authorization"] = f"Bearer {token}"
        root = client.post("/api/roots", json={"path": str(media), "label": "SYNTHETIC FIXTURE"}).json()
        job = client.post(f"/api/roots/{root['id']}/scan", json={}).json()
        app.state.scanner.run_job(job)
        assert client.post("/api/stats", json={}).json()["summary"]["count"] == 2
    assert hashes() == original
    app = create_app(config)
    requests = []
    @app.middleware("http")
    async def observe(request, call_next):
        response = await call_next(request)
        requests.append({"method": request.method, "path": request.url.path, "status": response.status_code})
        (staging / "requests.json").write_text(json.dumps(requests, ensure_ascii=False, indent=2), encoding="utf-8")
        assert hashes() == original, "Synthetic source bytes changed"
        (staging / "source-integrity.json").write_text(json.dumps({"unchanged": True, "sha256": original}), encoding="utf-8")
        return response
    print("Synthetic NAS ready at 127.0.0.1:18767 (API v1)", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=18767, access_log=False)


if __name__ == "__main__":
    main()
