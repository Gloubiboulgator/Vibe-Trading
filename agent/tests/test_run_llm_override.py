"""Per-run provider / model / effort choice from the chat (saved settings untouched)."""

from __future__ import annotations

import concurrent.futures
import contextvars
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api_server
from src.api.sessions_routes import RunLLMSelection, _resolve_run_llm
from src.config.accessor import current_llm_override, get_env_config, llm_override, reset_env_config

OPENROUTER_KEY = "sk-or-v1-" + "a1" * 32
ANTHROPIC_KEY = "sk-ant-api03-" + "b2" * 20


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join([
            "LANGCHAIN_PROVIDER=openrouter",
            "LANGCHAIN_MODEL_NAME=deepseek/deepseek-v4-pro",
            f"OPENROUTER_API_KEY={OPENROUTER_KEY}",
            f"ANTHROPIC_API_KEY={ANTHROPIC_KEY}",
            "DEEPSEEK_API_KEY=sk-xxx",
        ]) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(api_server, "ENV_PATH", env_path)
    monkeypatch.setattr(api_server, "LEGACY_ENV_PATH", tmp_path / "legacy" / ".env", raising=False)
    monkeypatch.setattr(api_server, "ENV_EXAMPLE_PATH", tmp_path / ".env.example")
    monkeypatch.setattr(api_server, "_baostock_supported", lambda: False)
    monkeypatch.setattr(api_server, "_baostock_installed", lambda: False)
    for name in ("API_AUTH_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return TestClient(api_server.app, client=("127.0.0.1", 50000))


def test_override_replaces_llm_fields_only_inside_the_scope() -> None:
    reset_env_config()
    before = get_env_config().llm
    with llm_override("anthropic", "claude-sonnet-5-5", "high"):
        llm = get_env_config().llm
        assert (llm.langchain_provider, llm.langchain_model_name, llm.langchain_reasoning_effort) == (
            "anthropic", "claude-sonnet-5-5", "high",
        )
        assert llm.timeout_seconds == before.timeout_seconds
    assert current_llm_override() is None
    assert get_env_config().llm.langchain_provider == before.langchain_provider


def test_override_reaches_a_worker_thread_through_copy_context() -> None:
    with llm_override("openrouter", "deepseek/deepseek-v4-pro", ""):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            seen = pool.submit(contextvars.copy_context().run,
                               lambda: get_env_config().llm.langchain_model_name).result()
            plain = pool.submit(lambda: current_llm_override()).result()
    assert seen == "deepseek/deepseek-v4-pro"
    assert plain is None  # without copy_context other threads are unaffected


def test_settings_lists_which_providers_have_a_saved_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The runtime exports the active key as OPENAI_API_KEY; that is not an OpenAI key.
    monkeypatch.setenv("OPENAI_API_KEY", OPENROUTER_KEY)
    providers = {p["name"]: p for p in client.get("/settings/llm").json()["providers"]}
    assert providers["openrouter"]["api_key_configured"] is True
    assert providers["anthropic"]["api_key_configured"] is True
    assert providers["deepseek"]["api_key_configured"] is False  # placeholder key
    assert providers["openai"]["api_key_configured"] is False


def test_resolve_run_llm_accepts_a_provider_with_a_saved_key(client: TestClient) -> None:
    got = _resolve_run_llm(RunLLMSelection(provider="Anthropic", model="claude-sonnet-5-5", reasoning_effort="HIGH"))
    assert got == ("anthropic", "claude-sonnet-5-5", "high")


@pytest.mark.parametrize("selection", [
    RunLLMSelection(provider="deepseek", model="deepseek-v4-pro"),      # no real key
    RunLLMSelection(provider="openai-codex", model="gpt-x"),           # login-based
    RunLLMSelection(provider="nope", model="x"),                        # unknown
    RunLLMSelection(provider="anthropic", model="claude-sonnet-5-5", reasoning_effort="bogus"),
])
def test_resolve_run_llm_rejects_unusable_choices(client: TestClient, selection: RunLLMSelection) -> None:
    with pytest.raises(HTTPException) as exc:
        _resolve_run_llm(selection)
    assert exc.value.status_code == 400


def test_model_name_rejects_unexpected_characters() -> None:
    with pytest.raises(ValueError):
        RunLLMSelection(provider="anthropic", model="claude; rm -rf /")
