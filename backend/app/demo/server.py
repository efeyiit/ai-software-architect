"""The demo site child process; token is inherited only from its launcher."""

from __future__ import annotations

import os
import sys

import uvicorn

from app.local_inference import (LocalAnswerProvider, LocalEmbeddingProvider,
                                 LocalRuntimeUnavailable, runtime_health)
from .main import create_demo_app


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def main() -> None:
    token = os.environ.get("ARIADNE_LOCAL_RUNTIME_TOKEN", "")
    if len(token) < 32:
        raise RuntimeError("Ephemeral local runtime token is missing")
    try:
        worker_pid = int(os.environ.get("ARIADNE_LOCAL_WORKER_PID", ""))
    except ValueError:
        raise RuntimeError("Local worker PID is missing") from None

    def readiness():
        if not _process_alive(worker_pid):
            return "unavailable"
        try:
            runtime_health(timeout_seconds=0.7)
            return "ready"
        except LocalRuntimeUnavailable:
            return "loading"

    app = create_demo_app(embedding=LocalEmbeddingProvider(token=token),
                          answer_provider=LocalAnswerProvider(token=token),
                          readiness=readiness)
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")


if __name__ == "__main__":
    main()
