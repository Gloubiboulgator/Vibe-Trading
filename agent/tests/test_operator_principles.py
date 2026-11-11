"""Operator amendments to the Output Principles (2026-11-11).

The principles forbid a verdict and make the model announce its refusal on
every "should I buy?", which the operator of a personal installation wanted
to change without editing the shipped text. The amendments live in the
runtime root, are edited from the Settings page, and land right after
principle 6. Without them the system prompt is the shipped one, unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api_server
from src.agent import operator_principles as op
from src.agent.context import ContextBuilder
from src.agent.memory import WorkspaceMemory
from src.tools import build_registry

pytestmark = pytest.mark.unit


@pytest.fixture
def runtime_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("VIBE_TRADING_HOME", str(tmp_path))
    return tmp_path


def _prompt() -> str:
    return ContextBuilder(build_registry(), WorkspaceMemory()).build_system_prompt()


def test_without_amendments_the_prompt_is_unchanged(runtime_root: Path) -> None:
    prompt = _prompt()
    assert "Operator amendments" not in prompt
    assert "{operator_principles}" not in prompt
    assert "exists to prevent.\n\n## Tools" in prompt


def test_amendments_follow_principle_six(runtime_root: Path) -> None:
    op.write_operator_principles("Give a clear verdict {when} asked.")
    prompt = _prompt()
    six = prompt.index("exists to prevent.")
    amendments = prompt.index("### Operator amendments")
    tools = prompt.index("## Tools")
    assert six < amendments < tools
    # Braces in the operator's text are kept literally, not formatted.
    assert "Give a clear verdict {when} asked." in prompt[amendments:tools]


def test_blank_text_removes_the_file_and_too_long_is_refused(runtime_root: Path) -> None:
    op.write_operator_principles("x")
    assert (runtime_root / op.OPERATOR_PRINCIPLES_FILE).exists()
    assert op.write_operator_principles("  \n ") == ""
    assert not (runtime_root / op.OPERATOR_PRINCIPLES_FILE).exists()
    with pytest.raises(ValueError):
        op.write_operator_principles("x" * (op.MAX_OPERATOR_PRINCIPLES_CHARS + 1))


def test_settings_page_reads_and_writes_the_amendments(
    runtime_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("API_AUTH_KEY", raising=False)
    client = TestClient(api_server.app, client=("127.0.0.1", 50000))

    assert client.get("/settings/output-principles").json()["text"] == ""
    saved = client.put("/settings/output-principles", json={"text": "  Avis net.\r\n  "})
    assert saved.status_code == 200
    assert saved.json()["text"] == "Avis net."
    assert client.get("/settings/output-principles").json()["text"] == "Avis net."
    assert (runtime_root / op.OPERATOR_PRINCIPLES_FILE).read_text(encoding="utf-8") == "Avis net.\n"

    too_long = client.put(
        "/settings/output-principles", json={"text": "x" * (op.MAX_OPERATOR_PRINCIPLES_CHARS + 1)}
    )
    assert too_long.status_code == 400


def test_a_remote_client_cannot_write_the_amendments(
    runtime_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("API_AUTH_KEY", "test-key")
    monkeypatch.delenv("VIBE_TRADING_TRUSTED_NETWORKS", raising=False)
    remote = TestClient(api_server.app, client=("8.8.8.8", 50000))
    response = remote.put("/settings/output-principles", json={"text": "anything"})
    assert response.status_code in (401, 403)
    assert not (runtime_root / op.OPERATOR_PRINCIPLES_FILE).exists()
