"""PEA mode: a session switch for users who invest through a French PEA (2026-11-08).

In the 2026-11-08 PEA conversation the agent proposed US stocks and the user
had to repeat "éligible PEA" twice. With the switch on, the agent gets the PEA
rules every turn and names resolve to their euro-area listing even when no
message says "PEA".
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

import src.providers.chat as chat_module
from src.agent.grounding import GroundingLedger
from src.agent.loop import AgentLoop
from src.agent.pea_mode import PEA_MODE_BLOCK, PEA_SOURCE_ID
from src.agent.resolution_context import ResolutionContext
from src.api.sessions_routes import SendMessageRequest
from src.config.accessor import reset_env_config
from src.providers.chat import ChatLLM, LLMResponse
from src.session.events import EventBus
from src.session.models import Attempt
from src.session.service import SessionService
from src.session.store import SessionStore

pytestmark = pytest.mark.unit

SANOFI = [
    {"symbol": "SNY.US", "name": "Sanofi", "market": "us", "type": "equity", "exchange": "NMS", "source": "yahoo", "cik": "0001121404"},
    {"symbol": "SAN.PA", "name": "SANOFI", "market": "global", "type": "equity", "exchange": "PAR", "source": "yahoo"},
]
NVIDIA = [
    {"symbol": "NVDA.US", "name": "英伟达", "market": "us", "type": "美股", "source": "eastmoney", "also_from": ["yahoo"], "cik": "0001045810"},
    {"symbol": "NVD.DE", "name": "NVIDIA Corp.", "market": "global", "type": "equity", "exchange": "GER", "source": "yahoo"},
]
PEA = (("eu", PEA_SOURCE_ID),)


def _lock(tmp_path: Path, query: str, candidates: list[dict[str, Any]], *, standing=()) -> str | None:
    ledger = GroundingLedger(
        run_dir=tmp_path, user_message=f"analyse {query}", history=None, standing_markets=standing,
    )
    payload = {"ok": True, "source": "symbol_search", "data": {"query": query, "candidates": candidates}}
    ledger.ingest_tool_result(
        tool_name="search_symbol",
        arguments={"query": query},
        result=json.dumps(payload, ensure_ascii=False),
        call_id=f"resolve-{query}",
        success=True,
    )
    record = next(r for r in ledger.identity_summary()["records"] if r["query"] == query)
    return record["symbol"] if record["status"] == "locked" else None


def test_pea_mode_locks_the_euro_listing_without_the_word_pea(tmp_path: Path) -> None:
    assert _lock(tmp_path, "Sanofi", SANOFI) == "SNY.US"
    assert _lock(tmp_path, "Sanofi", SANOFI, standing=PEA) == "SAN.PA"


def test_pea_mode_does_not_move_a_name_without_an_exact_euro_match(tmp_path: Path) -> None:
    assert _lock(tmp_path, "Nvidia", NVIDIA, standing=PEA) == "NVDA.US"


def test_the_standing_preference_is_not_explicit_and_holds_for_any_query() -> None:
    context = ResolutionContext.from_messages("compare Sanofi et Danone", standing_markets=PEA)
    [constraint] = context.constraints_for("Danone")
    assert (constraint.value, constraint.explicit, constraint.source_message_id) == ("eu", False, PEA_SOURCE_ID)
    assert ResolutionContext.from_messages("x", standing_markets=PEA, enabled=False).constraints == ()


def test_the_request_field_is_optional() -> None:
    assert SendMessageRequest(content="hi").pea_mode is None
    assert SendMessageRequest(content="hi", pea_mode=True).pea_mode is True


class _EmptyRegistry:
    _tools: dict = {}

    def get_definitions(self):
        return []


def _captured_user_message(monkeypatch, tmp_path: Path, **run_kwargs) -> str:
    monkeypatch.setenv("LANGCHAIN_PROVIDER", "deepseek")
    monkeypatch.setenv("LANGCHAIN_MODEL_NAME", "deepseek-test")
    reset_env_config()
    monkeypatch.setattr(chat_module, "build_llm", lambda **kwargs: object())
    llm = ChatLLM()
    seen: list[list[dict[str, Any]]] = []

    def _stream_chat(self, messages, *args, **kwargs):
        del self, args, kwargs
        seen.append(messages)
        return LLMResponse(content="ok")

    llm.stream_chat = MethodType(_stream_chat, llm)
    agent = AgentLoop(registry=_EmptyRegistry(), llm=llm, max_iterations=1)  # type: ignore[arg-type]
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    agent.memory.run_dir = str(run_dir)
    agent.run("quelles actions ?", **run_kwargs)
    return next(m["content"] for m in reversed(seen[0]) if m["role"] == "user")


def test_the_model_reads_the_pea_rules_only_when_the_mode_is_on(monkeypatch, tmp_path: Path) -> None:
    on = _captured_user_message(monkeypatch, tmp_path / "on", pea_mode=True)
    off = _captured_user_message(monkeypatch, tmp_path / "off")
    assert PEA_MODE_BLOCK in on and on.rstrip().endswith("quelles actions ?")
    assert "<pea-mode>" not in off


def test_the_rules_name_the_official_exclusions() -> None:
    for excluded in ("registered office", "SIIC", "preference shares", "warrants", "75 %"):
        assert excluded in PEA_MODE_BLOCK


@pytest.mark.parametrize(("config", "expected"), [({"pea_mode": True}, {"pea_mode": True}), ({}, {})])
def test_the_session_passes_its_mode_to_the_agent(monkeypatch, tmp_path: Path, config, expected) -> None:
    received: list[dict[str, Any]] = []

    class _Agent:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def run(self, *, user_message, history, session_id, **kwargs):
            del user_message, history, session_id
            received.append(kwargs)
            return {"status": "completed"}

    index = SimpleNamespace(index_session=lambda *a: None, index_message=lambda *a: None)
    monkeypatch.setattr("src.session.service.get_shared_index", lambda: index)
    monkeypatch.setattr("src.tools.build_registry", lambda **kwargs: object())
    monkeypatch.setattr("src.providers.chat.ChatLLM", lambda: SimpleNamespace(aclose=AsyncMock()))
    monkeypatch.setattr("src.memory.persistent.PersistentMemory", lambda: object())
    monkeypatch.setattr("src.agent.loop.AgentLoop", _Agent)
    monkeypatch.setattr("src.config.loader.load_runtime_agent_config", lambda overrides=None: object())
    monkeypatch.setattr("src.config.loader.sanitize_session_overrides", lambda overrides: dict(overrides))
    service = SessionService(
        store=SessionStore(tmp_path / "sessions"), event_bus=EventBus(), runs_dir=tmp_path / "runs",
    )
    attempt = Attempt(session_id="session-1", prompt="hello")
    asyncio.run(service._run_with_agent(attempt, messages=[], session_config=config))
    assert received == [expected]
