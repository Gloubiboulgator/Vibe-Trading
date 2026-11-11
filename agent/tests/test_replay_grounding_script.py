"""The grounding replay script finds released drafts and judges them (2026-11-11)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SPEC = importlib.util.spec_from_file_location(
    "replay_grounding", Path(__file__).resolve().parents[1] / "scripts" / "replay_grounding.py"
)
replay_grounding = importlib.util.module_from_spec(_SPEC)
sys.modules["replay_grounding"] = replay_grounding  # dataclasses look their module up
_SPEC.loader.exec_module(replay_grounding)

DRAFT = "Le cours de ABC.PA (Yahoo) est de 12,5 €.\n\n```figures\n12.5 | observed | close | get_market_data\n```\n"


def _write(tmp_path: Path, close: float, currency: str | None) -> Path:
    run = tmp_path / "run"
    (run / "artifacts").mkdir(parents=True)
    record = {"call_id": "c1", "tool": "get_market_data", "symbol": "ABC.PA", "source": "yahoo",
              "timestamp": "2026-11-10", "field": "close", "value": close, "status": "observed",
              "currency": currency}
    (run / "artifacts" / "grounding_evidence.json").write_text(json.dumps({"evidence": [record]}))
    session = tmp_path / "sessions" / "s1"
    session.mkdir(parents=True)
    events = [
        {"type": "start", "prompt": "Cours de ABC.PA ?"},
        {"type": "tool_call", "tool": "get_market_data", "args": {"codes": ["ABC.PA"], "run_dir": str(run)}},
        {"type": "answer_rejected", "content": DRAFT, "issues": []},
        {"type": "answer_released_redacted", "issues": []},
    ]
    (session / "trace.jsonl").write_text("\n".join(json.dumps(event) for event in events))
    return tmp_path / "sessions"


def test_a_released_draft_the_gate_now_accepts_is_clean(tmp_path) -> None:
    [draft] = list(replay_grounding.iter_drafts(_write(tmp_path, 12.5, "EUR"), only=None, include_all=False))
    assert draft.released and draft.line == 2
    assert replay_grounding.replay(draft).issues == []


def test_a_wrong_figure_still_fails_and_sets_the_exit_status(tmp_path) -> None:
    sessions = _write(tmp_path, 14.0, "EUR")
    assert replay_grounding.main(["--sessions-dir", str(sessions)]) == 1


def test_evidence_without_currencies_is_not_judged(tmp_path) -> None:
    [draft] = list(replay_grounding.iter_drafts(_write(tmp_path, 12.5, None), only=None, include_all=False))
    assert not replay_grounding.replay(draft).judged
