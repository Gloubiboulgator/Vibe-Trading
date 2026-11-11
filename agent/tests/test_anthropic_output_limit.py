"""A Claude model the library has no profile for gets a usable output limit (2026-11-11).

langchain-anthropic falls back to 4096 output tokens for a model it does not
know. claude-fable-5-2 spent all of them on reasoning twice and the run failed
with empty_model_response.
"""

from __future__ import annotations

import pytest

from src.config.accessor import reset_env_config
from src.providers import llm as llm_mod

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ANTHROPIC_MAX_TOKENS", raising=False)
    reset_env_config()
    yield
    reset_env_config()


def test_an_unprofiled_claude_model_gets_the_safe_limit() -> None:
    assert llm_mod._anthropic_output_limit("claude-fable-9-9") == llm_mod._ANTHROPIC_UNPROFILED_OUTPUT_LIMIT


def test_a_profiled_model_keeps_the_library_limit() -> None:
    assert llm_mod._anthropic_output_limit("claude-sonnet-5-5") is None


def test_a_non_claude_name_is_left_to_the_library() -> None:
    assert llm_mod._anthropic_output_limit("some-proxy-model") is None


def test_the_configured_limit_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_MAX_TOKENS", "16384")
    reset_env_config()
    assert llm_mod._anthropic_output_limit("claude-fable-9-9") == 16384
