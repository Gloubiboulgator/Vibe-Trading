"""Static-file serving rules for the bundled single-page application."""

from __future__ import annotations

from typing import Any

from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException


#: The page names the hashed bundle of the current build. Sent without this,
#: browsers reused a cached page after a rebuild and kept running the old
#: bundle (2026-11-11). It still revalidates by ETag, so an unchanged page
#: costs a 304. The hashed assets themselves keep the default caching.
HTML_CACHE_CONTROL = "no-cache"


def no_cache_html(response):
    """Mark an HTML response as revalidate-before-use."""
    if str(response.headers.get("content-type", "")).startswith("text/html"):
        response.headers["Cache-Control"] = HTML_CACHE_CONTROL
    return response


class SPAStaticFiles(StaticFiles):
    """Serve index.html for browser refreshes on client-side routes."""

    async def get_response(self, path: str, scope: dict[str, Any]):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            response = await super().get_response("index.html", scope)
        return no_cache_html(response)
