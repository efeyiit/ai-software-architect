"""One-command launcher for separate loopback site and model child processes."""

from __future__ import annotations

import os
import json
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
from time import sleep


ROOT = Path(__file__).resolve().parents[3]
SITE_PORT = 8765
MODEL_PORT = 8766


def _listener_pid(port: int) -> str | None:
    if sys.platform != "win32":
        return None
    try:
        output = subprocess.run(["netstat", "-ano", "-p", "tcp"],
                                capture_output=True, text=True, check=True).stdout
    except Exception:
        return None
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[1].endswith(f":{port}") and fields[3] == "LISTENING":
            return fields[4]
    return None


def _require_free_port(port: int) -> None:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            pid = _listener_pid(port)
            raise RuntimeError(f"127.0.0.1:{port} is already in use (PID {pid or 'unknown'}).") from exc


def _node_executable() -> str:
    located = shutil.which("node")
    if located:
        return located
    bundled = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"
    if bundled.is_file():
        return str(bundled)
    raise RuntimeError("Node.js is required to build the local demo frontend.")


def _build_frontend() -> Path:
    frontend = ROOT / "frontend"
    output = frontend / "dist"
    built = output / "index.html"
    sources = [frontend / "index.html", frontend / "package.json", frontend / "pnpm-lock.yaml",
               frontend / "tsconfig.json", frontend / "vite.config.ts"]
    source_tree = frontend / "src"
    if source_tree.is_dir():
        sources.extend(path for path in source_tree.rglob("*") if path.is_file())
    if built.is_file() and all(not path.is_file() or path.stat().st_mtime <= built.stat().st_mtime for path in sources):
        return output
    node = _node_executable()
    for script, arguments in (("typescript/bin/tsc", ["--noEmit"]),
                              ("vite/bin/vite.js", ["build"])):
        target = frontend / "node_modules" / script
        if not target.is_file():
            raise RuntimeError("Frontend dependencies are missing; install the pinned frontend packages.")
        subprocess.run([node, str(target), *arguments], cwd=frontend, check=True)
    if not (output / "index.html").is_file():
        raise RuntimeError("Frontend build did not produce index.html")
    return output


def _wait_for_children(model: subprocess.Popen, site: subprocess.Popen,
                       control_dir: Path | None = None, run_id: str | None = None) -> None:
    while site.poll() is None:
        if control_dir is not None and run_id is not None:
            request = control_dir / "stop.json"
            try:
                if json.loads(request.read_text(encoding="utf-8")).get("run_id") == run_id:
                    return
            except (OSError, ValueError):
                pass
        sleep(1)
    raise RuntimeError("Local demo site stopped unexpectedly")


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def main() -> None:
    _require_free_port(SITE_PORT)
    _require_free_port(MODEL_PORT)
    _build_frontend()
    model_python = ROOT / "training" / ".venv" / "Scripts" / "python.exe"
    model_script = ROOT / "training" / "local_runtime_server.py"
    if not model_python.is_file() or not model_script.is_file():
        raise RuntimeError("Pinned local model runtime is not installed.")
    token = secrets.token_urlsafe(32)
    run_id = secrets.token_urlsafe(16)
    control_dir_value = os.environ.get("ARIADNE_DEMO_CONTROL_DIR")
    control_dir = Path(control_dir_value).resolve() if control_dir_value else None
    if control_dir is not None:
        control_dir.mkdir(parents=True, exist_ok=True)
    child_env = os.environ.copy()
    child_env["ARIADNE_LOCAL_RUNTIME_TOKEN"] = token
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    model = subprocess.Popen([str(model_python), str(model_script)], cwd=ROOT / "training",
                             env=child_env, creationflags=flags)
    try:
        site_env = child_env.copy()
        site_env["ARIADNE_LOCAL_WORKER_PID"] = str(model.pid)
        site = subprocess.Popen([sys.executable, "-m", "app.demo.server"],
                                cwd=ROOT / "backend", env=site_env, creationflags=flags)
        try:
            if control_dir is not None:
                state_file = control_dir / "state.json"
                state_file.write_text(json.dumps({"run_id": run_id, "launcher_pid": os.getpid(),
                                                  "site_pid": site.pid, "model_pid": model.pid}), encoding="utf-8")
            print(f"Yerel demo: http://127.0.0.1:{SITE_PORT}/demo", flush=True)
            _wait_for_children(model, site, control_dir, run_id)
        except KeyboardInterrupt:
            pass
        finally:
            _stop(site)
            if control_dir is not None:
                state_file.unlink(missing_ok=True)
                request_file = control_dir / "stop.json"
                try:
                    if json.loads(request_file.read_text(encoding="utf-8")).get("run_id") == run_id:
                        request_file.unlink(missing_ok=True)
                except (OSError, ValueError):
                    pass
    finally:
        _stop(model)


if __name__ == "__main__":
    main()
