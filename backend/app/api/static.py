"""Same-origin static frontend for the authenticated product API."""

from pathlib import Path
import re

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException


class ProductStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
        route = path.replace("\\", "/").strip("/")
        if (scope["method"] in ("GET", "HEAD") and
                (route in ("login", "dashboard") or re.fullmatch(
                    r"repository/[^/]+(?:/(?:files|architecture|dependencies|findings|security|testing|documentation))?",
                    route))):
            return FileResponse(Path(self.directory) / "index.html")
        raise StarletteHTTPException(404)
