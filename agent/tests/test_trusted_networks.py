"""A private network the operator lists is trusted like loopback (2026-11-11).

The user wanted the web UI on a phone on the home Wi-Fi without an API key.
VIBE_TRADING_TRUSTED_NETWORKS lists such networks; public ranges are ignored so
the setting can never open keyless access to the internet.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api_server
from src.api.security import _is_local_client, _parse_trusted_networks
from src.config.accessor import reset_env_config

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    for name in ("API_AUTH_KEY", "VIBE_TRADING_TRUSTED_NETWORKS", "API_ALLOWED_HOSTS",
                 "VIBE_TRADING_TRUST_DOCKER_LOOPBACK"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(api_server, "_API_KEY", "")
    reset_env_config()
    yield
    reset_env_config()


def _request(host: str) -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=host))


def test_a_lan_client_is_not_trusted_by_default() -> None:
    assert not _is_local_client(_request("192.168.1.42"))


def test_a_listed_private_network_is_trusted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIBE_TRADING_TRUSTED_NETWORKS", "192.168.1.0/24")
    reset_env_config()
    assert _is_local_client(_request("192.168.1.42"))
    assert not _is_local_client(_request("192.168.2.42"))
    assert not _is_local_client(_request("203.0.113.10"))


@pytest.mark.parametrize("raw", ["0.0.0.0/0", "8.8.8.0/24", "::/0", "not-a-network"])
def test_public_or_unreadable_networks_are_ignored(raw: str) -> None:
    assert _parse_trusted_networks(raw) == []


def test_a_phone_on_the_wifi_can_write_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIBE_TRADING_TRUSTED_NETWORKS", "192.168.1.0/24")
    monkeypatch.setenv("API_ALLOWED_HOSTS", "192.168.1.165")
    reset_env_config()
    phone = TestClient(api_server.app, client=("192.168.1.42", 50000), base_url="http://192.168.1.165:8899")
    assert phone.post("/sessions", json={}).status_code != 401
    stranger = TestClient(api_server.app, client=("203.0.113.10", 50000), base_url="http://192.168.1.165:8899")
    assert stranger.post("/sessions", json={}).status_code in (401, 403)
