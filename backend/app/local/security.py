"""Local-only host/origin checks and bounded request buffering."""

from http.cookies import CookieError, SimpleCookie
from secrets import compare_digest
import re

from starlette.responses import JSONResponse


class LocalBoundary:
    def __init__(self, app, *, session: str, csrf: str, max_body_bytes: int):
        self.app, self.session, self.csrf, self.max_body = app, session, csrf, max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        host = headers.get("host", "")
        origin = headers.get("origin")
        expected_origin = scope.get("scheme", "http") + "://" + host
        if not re.fullmatch(r"(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?", host) or (origin is not None and origin != expected_origin) or headers.get("sec-fetch-site") == "cross-site":
            return await JSONResponse({"detail": "LOCAL_ORIGIN_REQUIRED"}, status_code=403)(scope, receive, send)
        if scope["path"].startswith("/api/local/") and scope["path"] != "/api/local/session":
            cookies = SimpleCookie()
            try:
                cookies.load(headers.get("cookie", ""))
                cookie = cookies.get("ariadne_local")
                valid = cookie and compare_digest(cookie.value, self.session)
            except (CookieError, ValueError, TypeError):
                valid = False
            if not valid:
                return await JSONResponse({"detail": "LOCAL_SESSION_REQUIRED"}, status_code=401)(scope, receive, send)
        if scope["method"] not in ("GET", "HEAD", "OPTIONS"):
            if not compare_digest(headers.get("x-csrf-token", "").encode(), self.csrf.encode()):
                return await JSONResponse({"detail": "CSRF_REQUIRED"}, status_code=403)(scope, receive, send)
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > self.max_body:
                    return await JSONResponse({"detail": "BODY_TOO_LARGE"}, status_code=413)(scope, receive, send)
                if not message.get("more_body", False):
                    break
            delivered = False
            original_receive = receive
            async def bounded_receive():
                nonlocal delivered
                if delivered:
                    return await original_receive()
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            receive = bounded_receive
        await self.app(scope, receive, send)
