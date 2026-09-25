"""Separate local demo ASGI app. It never imports production identity storage."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import re
from threading import Lock
from typing import Callable, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.rag.chat import RepositoryChat
from app.rag.indexing import AuthorizedScope, QdrantIndex
from .fixture import (DEMO_COMMIT_SHA, DEMO_OWNER, DEMO_REPOSITORY_ID,
                      DEMO_SOURCE_ID, DEMO_SOURCES, demo_snapshot)


ReadyState = Literal["ready", "loading", "unavailable"]


class DemoQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class DemoStaticFiles(StaticFiles):
    """Serve the SPA shell only for Ariadne's known browser routes."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
        if (scope["method"] in ("GET", "HEAD") and
                (path.replace("\\", "/") in ("dashboard", "login", "demo") or re.fullmatch(
                    r"repository/[^/]+(?:/(?:files|architecture|dependencies|findings|security|testing|documentation))?/?", path.replace("\\", "/")))):
            return FileResponse(Path(self.directory) / "index.html")
        raise StarletteHTTPException(404)


def create_demo_app(*, embedding=None, answer_provider=None,
                    readiness: Callable[[], ReadyState] | None = None,
                    frontend_dir: Path | None = None) -> FastAPI:
    """Serve only bundled fixture data and a local, source-cited model answer."""
    app = FastAPI(title="Ariadne Yerel Demo", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    lock = Lock()
    chat: RepositoryChat | None = None

    def state() -> ReadyState:
        if embedding is None or answer_provider is None:
            return "unavailable"
        try:
            value = readiness() if readiness is not None else "ready"
        except Exception:
            return "unavailable"
        return value if value in ("ready", "loading", "unavailable") else "unavailable"

    def initialize_chat() -> RepositoryChat:
        nonlocal chat
        with lock:
            if chat is None:
                scope = AuthorizedScope(DEMO_OWNER, DEMO_REPOSITORY_ID,
                                        DEMO_SOURCE_ID, DEMO_COMMIT_SHA, False)
                index = QdrantIndex(QdrantClient(":memory:"),
                                    lambda owner, repository_id: scope if
                                    (owner, repository_id) == (DEMO_OWNER, DEMO_REPOSITORY_ID) else None,
                                    embedding, collection_prefix="ariadne_demo")
                index.index_snapshot(DEMO_OWNER, DEMO_REPOSITORY_ID,
                                     demo_snapshot(), DEMO_SOURCES)
                chat = RepositoryChat(index, answer_provider)
            return chat

    @app.get("/demo/meta")
    def meta():
        return {"mode": "local_demo", "label": "Yerel demo",
                "repository_id": DEMO_REPOSITORY_ID, "commit_sha": DEMO_COMMIT_SHA,
                "data_origin": "bundled_synthetic", "model_status": state()}

    @app.post("/demo/chat")
    def ask(body: DemoQuestion, request: Request):
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
            raise HTTPException(403, detail="demo_origin_denied")
        if state() != "ready":
            return {"status": "unavailable", "answer": "Yerel model henüz hazır değil.",
                    "origin": "none", "claims": [], "commit_sha": DEMO_COMMIT_SHA}
        try:
            return asdict(initialize_chat().ask(DEMO_OWNER, DEMO_REPOSITORY_ID, body.question))
        except Exception:
            return {"status": "unavailable", "answer": "Yerel model şu anda kullanılamıyor.",
                    "origin": "none", "claims": [], "commit_sha": DEMO_COMMIT_SHA}

    site = frontend_dir or Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if site.is_dir() and (site / "index.html").is_file():
        @app.get("/", include_in_schema=False)
        def demo_home():
            return RedirectResponse("/demo", status_code=307)

        app.mount("/", DemoStaticFiles(directory=site, html=True), name="demo_site")
    else:
        @app.get("/")
        def no_build():
            return JSONResponse({"status": "unavailable", "message": "Frontend build is missing."}, status_code=503)
    return app
