"""Ariadne HTTP application with fail-closed identity and analysis routes."""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from fastapi import FastAPI

from app.api.router import RuntimeProxy, create_api_router
from app.api.static import ProductStaticFiles
from app.security.identity.http import (build_identity_http_from_env,
                                        create_identity_router, require_session_user)
from app.services.reporting import ApiRuntime


logger = logging.getLogger(__name__)
runtime_proxy = RuntimeProxy()


@asynccontextmanager
async def lifespan(application: FastAPI):
    identity = None
    try:
        identity = build_identity_http_from_env()
        runtime = ApiRuntime.from_env(identity)
        application.state.identity_http = identity
        runtime_proxy.runtime = runtime
    except Exception:
        # Credentials, database, or schema unavailable: routes remain 503.
        if identity is not None:
            identity.close()
        logger.warning("ariadne_api_unconfigured")
    try:
        yield
    finally:
        runtime_proxy.runtime = None
        if identity is not None:
            identity.close()
        if hasattr(application.state, "identity_http"):
            del application.state.identity_http


app = FastAPI(title="Ariadne API", version="0.2.0", lifespan=lifespan)
app.include_router(create_identity_router())
app.include_router(create_api_router(require_session_user, runtime_proxy))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


frontend = Path(os.getenv("ARIADNE_FRONTEND_DIST") or Path(__file__).resolve().parents[2] / "frontend" / "dist")
if (frontend / "index.html").is_file():
    app.mount("/", ProductStaticFiles(directory=frontend, html=True), name="product_site")
