"""Start the local UI, optionally with the already-installed model worker."""

import argparse
import os
from pathlib import Path
import secrets
import subprocess

from app.api.local_launcher import _frontend
from app.local.main import create_local_app


def main():
    parser = argparse.ArgumentParser(description="Run Ariadne locally without a GitHub account")
    parser.add_argument("--with-ai", action="store_true", help="Use the installed local model; no model download")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    _frontend()
    worker = None
    if args.with_ai:
        python = root / "training" / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            raise SystemExit("Local model environment is missing. See training/LOCAL-RUNTIME.md or start without --with-ai.")
        from app.api.local_launcher import _free
        _free(8766)
        os.environ["ARIADNE_LOCAL_RUNTIME_TOKEN"] = secrets.token_urlsafe(32)
        os.environ["ARIADNE_LOCAL_RUNTIME_URL"] = "http://127.0.0.1:8766"
        env = dict(os.environ, ARIADNE_LOCAL_RUNTIME_PORT="8766", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        worker = subprocess.Popen([str(python), str(root / "training" / "local_runtime_server.py")], cwd=root / "training", env=env,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        import uvicorn
        print("Ariadne: http://127.0.0.1:8080 — press Ctrl+C to stop.")
        uvicorn.run(create_local_app(Path(os.environ.get("ARIADNE_LOCAL_DATA", str(root / "storage" / "local")))), host="127.0.0.1", port=8080)
    finally:
        if worker is not None:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()


if __name__ == "__main__":
    main()
