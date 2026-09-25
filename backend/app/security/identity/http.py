"""GitHub login routes and server-side cookie sessions for trusted API callers."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .service import IdentityError, OAuthConfig, OAuthService, TokenCipher
from .store import PostgresIdentityStore


SESSION_COOKIE = "__Host-ariadne_session"
BROWSER_COOKIE = "__Host-ariadne_login_binding"
SESSION_SECONDS = 8 * 60 * 60
LOGIN_SECONDS = 10 * 60


def _digest(raw: str) -> bytes:
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _csrf(raw: str) -> str:
    return hashlib.sha256(("ariadne-csrf:" + raw).encode("utf-8")).hexdigest()


def _problem(error: IdentityError) -> HTTPException:
    status = 400
    if error.code == "CONFIGURATION_ERROR":
        status = 503
    elif error.code in ("GITHUB_UNAVAILABLE", "INVALID_GITHUB_RESPONSE"):
        status = 502
    elif error.code in ("ACCOUNT_MISMATCH", "ACCOUNT_CONFLICT"):
        status = 409
    elif error.code in ("GITHUB_ACCESS_DENIED", "INSUFFICIENT_SCOPE"):
        status = 403
    return HTTPException(status_code=status, detail={"code": error.code.lower(),
                                                      "message": str(error)})


class IdentityHTTP:
    def __init__(self, oauth: OAuthService, store: PostgresIdentityStore,
                 clock=None, connection=None):
        callback = urlsplit(oauth.config.redirect_uri)
        if callback.path != "/auth/github/callback":
            raise IdentityError("CONFIGURATION_ERROR", "GitHub callback must use /auth/github/callback")
        self.oauth = oauth
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.connection = connection

    def close(self):
        if self.connection is not None:
            self.connection.close()

    def session_user(self, request: Request) -> str:
        raw = request.cookies.get(SESSION_COOKIE)
        if not isinstance(raw, str) or not 20 <= len(raw) <= 200:
            raise HTTPException(401, detail={"code": "login_required"})
        user_id = self.store.load_session(_digest(raw))
        if user_id is None:
            raise HTTPException(401, detail={"code": "login_required"})
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            submitted = request.headers.get("X-Ariadne-CSRF", "")
            if not hmac.compare_digest(submitted, _csrf(raw)):
                raise HTTPException(403, detail={"code": "csrf_required"})
        return user_id

    def issue_session(self, user_id: str, response: RedirectResponse, request: Request):
        raw = secrets.token_urlsafe(32)
        previous = request.cookies.get(SESSION_COOKIE)
        self.store.replace_session(user_id, _digest(raw),
                                   self.clock() + timedelta(seconds=SESSION_SECONDS),
                                   _digest(previous) if previous else None)
        response.set_cookie(SESSION_COOKIE, raw, max_age=SESSION_SECONDS, path="/",
                            secure=True, httponly=True, samesite="lax")


def _configured(request: Request) -> IdentityHTTP:
    identity = getattr(request.app.state, "identity_http", None)
    if not isinstance(identity, IdentityHTTP):
        raise HTTPException(503, detail={"code": "configuration_unavailable"})
    return identity


def require_session_user(request: Request) -> str:
    """FastAPI dependency: verified server-side cookie only, never a user header."""
    return _configured(request).session_user(request)


def create_identity_router() -> APIRouter:
    router = APIRouter()

    @router.get("/auth/github/login")
    def github_login(request: Request):
        identity = _configured(request)
        binding = secrets.token_urlsafe(32)
        try:
            url = identity.oauth.start_login(binding)
        except IdentityError as exc:
            raise _problem(exc) from None
        response = RedirectResponse(url, status_code=302)
        response.set_cookie(BROWSER_COOKIE, binding, max_age=LOGIN_SECONDS, path="/",
                            secure=True, httponly=True, samesite="lax")
        return response

    @router.post("/auth/github/private")
    def github_private(request: Request, user_id: str = Depends(require_session_user)):
        identity = _configured(request)
        try:
            url = identity.oauth.start(user_id, "private")
        except IdentityError as exc:
            raise _problem(exc) from None
        return RedirectResponse(url, status_code=302)

    @router.get("/auth/github/callback")
    def github_callback(request: Request, state: str = "", code: str = ""):
        identity = _configured(request)
        try:
            if state.startswith("l_"):
                binding = request.cookies.get(BROWSER_COOKIE, "")
                user_id = identity.oauth.finish_login(binding, state, code)
            elif state.startswith("p_"):
                user_id = require_session_user(request)
                identity.oauth.finish(user_id, "private", state, code)
            else:
                raise IdentityError("INVALID_STATE", "Unknown GitHub login state")
            response = RedirectResponse("/", status_code=303)
            identity.issue_session(user_id, response, request)
            response.delete_cookie(BROWSER_COOKIE, path="/", secure=True, httponly=True,
                                   samesite="lax")
            return response
        except IdentityError as exc:
            raise _problem(exc) from None

    @router.get("/auth/me")
    def auth_me(request: Request, user_id: str = Depends(require_session_user)):
        raw = request.cookies[SESSION_COOKIE]
        return {"user_id": user_id, "csrf_token": _csrf(raw)}

    @router.post("/auth/logout")
    def logout(request: Request, user_id: str = Depends(require_session_user)):
        identity = _configured(request)
        identity.store.delete_session(_digest(request.cookies[SESSION_COOKIE]))
        response = JSONResponse({"status": "logged_out"})
        response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True,
                               samesite="lax")
        response.delete_cookie(BROWSER_COOKIE, path="/", secure=True, httponly=True,
                               samesite="lax")
        return response

    return router


def build_identity_http_from_env() -> IdentityHTTP:
    """Open dedicated autocommit storage; caller owns close() at shutdown."""
    dsn = os.getenv("ARIADNE_DATABASE_URL", "")
    if not dsn:
        raise IdentityError("CONFIGURATION_ERROR", "Database URL is required for GitHub login")
    config = OAuthConfig.from_env()
    cipher = TokenCipher.from_env()
    connection = None
    try:
        connection = psycopg.connect(dsn, autocommit=True, connect_timeout=5)
        schema = connection.execute(
            """SELECT to_regclass('users'), to_regclass('oauth_pending_states'),
                      to_regclass('oauth_login_attempts'), to_regclass('oauth_sessions'),
                      to_regclass('oauth_connections')"""
        ).fetchone()
        if not all(schema):
            raise IdentityError("CONFIGURATION_ERROR", "GitHub identity database tables are not installed")
        store = PostgresIdentityStore(connection)
        return IdentityHTTP(OAuthService(config, cipher, store), store, connection=connection)
    except IdentityError:
        if connection is not None:
            connection.close()
        raise
    except Exception:
        if connection is not None:
            connection.close()
        raise IdentityError("CONFIGURATION_ERROR", "GitHub identity database is unavailable") from None
