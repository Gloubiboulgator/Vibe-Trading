"""The SPA page is sent with no-cache so a rebuilt bundle is picked up (2026-11-11).

Without a Cache-Control header, browsers reused a cached index.html after the
frontend was rebuilt and kept running the previous bundle.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.spa import HTML_CACHE_CONTROL, SPAStaticFiles

pytestmark = pytest.mark.unit


def _client(tmp_path) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><script src=/assets/app-1.js></script>")
    (tmp_path / "assets" / "app-1.js").write_text("console.log(1)")
    app = FastAPI()
    app.mount("/", SPAStaticFiles(directory=str(tmp_path), html=True), name="frontend")
    return TestClient(app)


@pytest.mark.parametrize("path", ["/", "/settings", "/agent"])
def test_the_page_must_be_revalidated(tmp_path, path) -> None:
    response = _client(tmp_path).get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == HTML_CACHE_CONTROL


def test_hashed_assets_keep_their_default_caching(tmp_path) -> None:
    response = _client(tmp_path).get("/assets/app-1.js")
    assert response.status_code == 200
    assert "cache-control" not in response.headers
