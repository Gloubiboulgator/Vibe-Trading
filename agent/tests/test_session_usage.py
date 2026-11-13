"""A conversation's tokens and cost, for the model bar (2026-11-13). Made-up values."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.llm_pricing import usage_cost
from src.session.usage import session_usage

pytestmark = pytest.mark.unit


def test_each_kind_of_token_is_billed_at_its_own_rate() -> None:
    totals = {
        "input_tokens": 1_000_000 + 2_000_000 + 400_000,  # uncached + read + written
        "cache_read_tokens": 2_000_000,
        "cache_creation_tokens": 400_000,
        "output_tokens": 100_000,
    }
    # 1M × 4 + 2M × 0.20 + 0.4M × 5 + 0.1M × 20
    assert usage_cost("claude-opus-5-5", totals) == pytest.approx(4.0 + 0.4 + 2.0 + 2.0)
    assert usage_cost("anthropic/claude-opus-5-5", totals) == pytest.approx(8.4)


def test_a_model_without_a_known_price_has_no_cost() -> None:
    assert usage_cost("deepseek/deepseek-v4-pro", {"input_tokens": 10, "output_tokens": 5}) is None
    assert usage_cost(None, {"input_tokens": 10}) is None


def _run(tmp_path: Path, session: str, attempt: str, model: str, totals: dict | None) -> None:
    run_dir = tmp_path / "runs" / attempt
    run_dir.mkdir(parents=True)
    if totals is not None:
        (run_dir / "llm_usage.json").write_text(json.dumps({"model": model, "totals": totals}))
    attempt_dir = tmp_path / "sessions" / session / "attempts" / attempt
    attempt_dir.mkdir(parents=True)
    (attempt_dir / "attempt.json").write_text(json.dumps({"attempt_id": attempt, "run_dir": str(run_dir)}))


def test_a_session_sums_its_runs_and_counts_the_unpriced_ones(tmp_path: Path) -> None:
    _run(tmp_path, "s1", "a1", "claude-sonnet-5-5", {"input_tokens": 1_000_000, "output_tokens": 100_000})
    _run(tmp_path, "s1", "a2", "deepseek/deepseek-v4-pro", {"input_tokens": 500, "output_tokens": 50})
    _run(tmp_path, "s1", "a3", "claude-sonnet-5-5", None)  # a run still starting
    _run(tmp_path, "s2", "b1", "claude-opus-5-5", {"input_tokens": 9_000_000, "output_tokens": 9})

    usage = session_usage(tmp_path / "sessions", "s1")

    assert usage["input_tokens"] == 1_000_500
    assert usage["output_tokens"] == 100_050
    assert usage["total_tokens"] == 1_100_550
    assert usage["cost_usd"] == pytest.approx(2.0 + 1.0)
    assert (usage["runs"], usage["unpriced_runs"]) == (2, 1)


def test_a_session_without_runs_has_no_cost(tmp_path: Path) -> None:
    usage = session_usage(tmp_path / "sessions", "empty")
    assert (usage["total_tokens"], usage["cost_usd"], usage["runs"]) == (0, None, 0)
