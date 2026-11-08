"""Anthropic model discovery uses /v1/models with x-api-key (2026-11-08).

"Load models" for Anthropic sent ``Authorization: Bearer`` to ``/models``, which the
Messages API refuses, so only the catalog default was ever offered.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from src.api import settings_routes

pytestmark = pytest.mark.unit

REAL_ASYNC_CLIENT = httpx.AsyncClient
PROVIDER = settings_routes.LLM_PROVIDER_BY_NAME["anthropic"]


def _run(monkeypatch: pytest.MonkeyPatch, handler, *, base_url: str = "https://api.anthropic.com"):
    real_client = REAL_ASYNC_CLIENT
    monkeypatch.setattr(
        settings_routes.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return asyncio.run(
        settings_routes._list_provider_models(PROVIDER, base_url=base_url, api_key="sk-ant-test")
    )


@pytest.mark.parametrize("base_url", ["https://api.anthropic.com", "https://api.anthropic.com/v1/"])
def test_lists_models_with_the_anthropic_endpoint_and_headers(monkeypatch, base_url) -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"data": [{"id": "claude-opus-5-5"}, {"id": "claude-haiku-5-5"}], "has_more": False}
        )

    result = _run(monkeypatch, handler, base_url=base_url)
    request = seen[0]
    assert str(request.url) == "https://api.anthropic.com/v1/models?limit=1000"
    assert request.headers["x-api-key"] == "sk-ant-test"
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert "authorization" not in request.headers
    assert result.source == "provider"
    assert {"claude-opus-5-5", "claude-haiku-5-5"} <= set(result.models)


def test_a_refused_list_falls_back_to_the_default(monkeypatch) -> None:
    result = _run(monkeypatch, lambda _: httpx.Response(401, json={"error": "unauthorized"}))
    assert result.source == "default"
    assert result.warning_code == "model_list_unavailable"
    assert result.models == [PROVIDER.default_model]


def test_other_providers_keep_the_bearer_request(monkeypatch) -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "deepseek/deepseek-v4-pro"}]})

    real_client = REAL_ASYNC_CLIENT
    monkeypatch.setattr(
        settings_routes.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    provider = settings_routes.LLM_PROVIDER_BY_NAME["openrouter"]
    asyncio.run(
        settings_routes._list_provider_models(
            provider, base_url="https://openrouter.ai/api/v1", api_key="sk-or-test"
        )
    )
    assert seen[0].headers["authorization"] == "Bearer sk-or-test"
    assert str(seen[0].url) == "https://openrouter.ai/api/v1/models"
