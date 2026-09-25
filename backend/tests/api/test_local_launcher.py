import json
import os
from hashlib import sha256

import pytest

from app.api import local_launcher


@pytest.mark.parametrize("asset_changed", [False, True])
def test_frontend_build_tracks_public_assets(tmp_path, monkeypatch, asset_changed):
    frontend = tmp_path / "frontend"
    for directory in ("public", "dist", "node_modules/typescript/bin", "node_modules/vite/bin"):
        (frontend / directory).mkdir(parents=True)
    built = frontend / "dist/index.html"
    asset = frontend / "public/logo.png"
    built.write_text("built shell", encoding="utf-8")
    asset.write_bytes(b"logo")
    os.utime(built, (200, 200))
    os.utime(asset, (300, 300) if asset_changed else (100, 100))
    node = tmp_path / "node.exe"
    node.touch()
    (frontend / "node_modules/typescript/bin/tsc").touch()
    (frontend / "node_modules/vite/bin/vite.js").touch()
    monkeypatch.setattr(local_launcher, "ROOT", tmp_path)
    monkeypatch.setattr(local_launcher.shutil, "which", lambda name: str(node))
    calls = []
    monkeypatch.setattr(local_launcher.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    assert local_launcher._frontend() == built.parent
    assert len(calls) == (2 if asset_changed else 0)


class LiveProcess:
    def poll(self):
        return None


class HealthResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, count):
        return json.dumps(self.payload).encode()


def test_model_readiness_rejects_old_runtime_fingerprint(tmp_path, monkeypatch):
    source = tmp_path / "worker.py"
    source.write_text("current code", encoding="utf-8")
    health = {"status": "ready", "embedding_model_id": local_launcher.MODEL_ID,
              "model_id": local_launcher.ANSWER_MODEL_ID,
              "prompt_version": local_launcher.PROMPT_VERSION,
              "runtime_code_sha256": "0" * 64}
    monkeypatch.setattr(local_launcher, "urlopen", lambda *args, **kwargs: HealthResponse(health))
    with pytest.raises(RuntimeError, match="wrong runtime fingerprint"):
        local_launcher._ready_model(LiveProcess(), source)
    health["runtime_code_sha256"] = sha256(source.read_bytes()).hexdigest()
    local_launcher._ready_model(LiveProcess(), source)
