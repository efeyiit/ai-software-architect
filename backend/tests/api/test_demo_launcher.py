import os
import json

from app.demo import __main__ as launcher


def test_launcher_scopes_ephemeral_token_to_two_loopback_children(tmp_path, monkeypatch):
    launched = []
    # This process-ownership test never launches a model. Supply its own file
    # preconditions so a clean checkout does not need the optional CUDA runtime.
    runtime_python = tmp_path / "training/.venv/Scripts/python.exe"
    runtime_python.parent.mkdir(parents=True)
    runtime_python.touch()
    (tmp_path / "training/local_runtime_server.py").touch()
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.delenv("ARIADNE_DEMO_CONTROL_DIR", raising=False)

    class Process:
        def __init__(self, args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.pid = 8100 + len(launched)
            self.stopped = False
            launched.append(self)

        def poll(self):
            return None if not self.stopped else 0

        def terminate(self):
            self.stopped = True

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(launcher, "_require_free_port", lambda port: None)
    monkeypatch.setattr(launcher, "_build_frontend", lambda: launcher.ROOT / "frontend" / "dist")
    monkeypatch.setattr(launcher.subprocess, "Popen", Process)
    monkeypatch.setattr(launcher.secrets, "token_urlsafe", lambda count: "x" * 43)
    monkeypatch.setattr(launcher, "_wait_for_children", lambda *args: None)
    before = os.environ.get("ARIADNE_LOCAL_RUNTIME_TOKEN")

    launcher.main()

    assert len(launched) == 2
    assert all(process.kwargs["env"]["ARIADNE_LOCAL_RUNTIME_TOKEN"] == "x" * 43
               for process in launched)
    assert all("x" * 43 not in str(process.args) for process in launched)
    assert launched[1].kwargs["env"]["ARIADNE_LOCAL_WORKER_PID"] == str(launched[0].pid)
    assert launched[0].stopped and launched[1].stopped
    assert os.environ.get("ARIADNE_LOCAL_RUNTIME_TOKEN") == before


def test_launcher_reuses_fresh_frontend_build(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "dist").mkdir()
    (frontend / "index.html").write_text("source", encoding="utf-8")
    (frontend / "dist" / "index.html").write_text("build", encoding="utf-8")
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "_node_executable", lambda: "node")
    calls = []
    monkeypatch.setattr(launcher.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    assert launcher._build_frontend() == frontend / "dist"
    assert calls == []


def test_launcher_honors_only_matching_stop_request(tmp_path, monkeypatch):
    class Process:
        def poll(self):
            return None

    control = tmp_path / "control"
    control.mkdir()
    (control / "stop.json").write_text(json.dumps({"run_id": "other"}), encoding="utf-8")
    sleeps = []

    def stop_after_one_poll(seconds):
        sleeps.append(seconds)
        (control / "stop.json").write_text(json.dumps({"run_id": "ours"}), encoding="utf-8")

    monkeypatch.setattr(launcher, "sleep", stop_after_one_poll)
    launcher._wait_for_children(Process(), Process(), control, "ours")
    assert sleeps == [1]
