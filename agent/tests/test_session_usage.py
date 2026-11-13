"""A conversation's tokens and cost, for the model bar (2026-11-13). Made-up values."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.llm_pricing import load_openrouter_catalog, openrouter_price, usage_cost
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


def _run(
    tmp_path: Path, session: str, attempt: str, model: str, totals: dict | None, **extra: str
) -> None:
    run_dir = tmp_path / "runs" / attempt
    run_dir.mkdir(parents=True)
    if totals is not None:
        (run_dir / "llm_usage.json").write_text(json.dumps({"model": model, "totals": totals, **extra}))
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


# A made-up OpenRouter catalog entry: per-token prices as strings, a cheaper
# rate on weekends, as the real catalog spells them.
_CATALOG = {
    "maker/model-x": {
        "prompt": "0.000001", "completion": "0.000004", "input_cache_read": "0.0000001",
        "overrides": [{"utc_days": ["saturday", "sunday"], "prompt": "0.0000005", "completion": "0.000002",
                       "input_cache_read": "0.00000005"}],
    },
    "maker/model-free:free": {"prompt": "0", "completion": "0"},
}


def test_an_openrouter_run_is_priced_from_the_catalog_at_its_hour(tmp_path: Path) -> None:
    totals = {"input_tokens": 3_000_000, "cache_read_tokens": 1_000_000, "output_tokens": 500_000}
    _run(tmp_path, "s1", "a1", "maker/model-x", totals, provider="openrouter", updated_at="2026-11-11T12:00:00Z")
    _run(tmp_path, "s1", "a2", "maker/model-x", totals, provider="openrouter", updated_at="2026-11-14T12:00:00Z")
    _run(tmp_path, "s1", "a3", "maker/model-free:free", totals, provider="openrouter")
    _run(tmp_path, "s1", "a4", "maker/not-listed", totals, provider="openrouter")
    loads: list[int] = []

    usage = session_usage(tmp_path / "sessions", "s1", load_catalog=lambda: loads.append(1) or _CATALOG)

    weekday = 2_000_000 * 1.0 + 1_000_000 * 0.1 + 500_000 * 4.0  # per million: 2 + 0.1 + 2
    assert usage["cost_usd"] == pytest.approx((weekday + weekday / 2) / 1_000_000)
    assert (usage["runs"], usage["unpriced_runs"]) == (4, 1)
    assert loads == [1]


def test_a_model_without_a_cache_price_bills_cached_tokens_as_input() -> None:
    price = openrouter_price({"m": {"prompt": "0.000002", "completion": "0.000003"}}, "m")
    assert price is not None and price.cache_read == price.cache_write == pytest.approx(2.0)


def test_the_catalog_is_downloaded_once_a_day_and_kept_when_offline(tmp_path: Path) -> None:
    clock = [1_000_000.0]
    calls: list[int] = []

    def fetch() -> dict:
        calls.append(1)
        return {"maker/model-x": _CATALOG["maker/model-x"]}

    def offline() -> dict:
        calls.append(1)
        raise OSError("no network")

    assert load_openrouter_catalog(tmp_path, fetch=fetch, now=lambda: clock[0])
    clock[0] += 3600
    assert load_openrouter_catalog(tmp_path, fetch=fetch, now=lambda: clock[0])
    assert calls == [1]

    clock[0] += 24 * 3600
    assert "maker/model-x" in (load_openrouter_catalog(tmp_path, fetch=offline, now=lambda: clock[0]) or {})
    clock[0] += 60
    assert "maker/model-x" in (load_openrouter_catalog(tmp_path, fetch=offline, now=lambda: clock[0]) or {})
    assert calls == [1, 1]  # a failure is retried after 15 minutes, not on every request
