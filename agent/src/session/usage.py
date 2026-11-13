"""A conversation's token usage and cost, summed over its runs' ``llm_usage.json``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from src.agent.llm_pricing import load_openrouter_catalog, run_price, usage_cost
from src.agent.llm_usage import LLM_USAGE_ARTIFACT

_TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def session_usage(
    sessions_dir: Path,
    session_id: str,
    *,
    load_catalog: Callable[[], Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Sum every run of one session.

    OpenRouter's catalog is loaded only when a run used OpenRouter;
    ``load_catalog`` replaces the cached download (tests).

    Returns:
        Token totals, ``cost_usd`` over the runs whose model has a known price
        (None when none has), ``unpriced_runs`` for the others, and ``runs``.
    """
    totals = {key: 0 for key in _TOKEN_KEYS}
    cost: float | None = None
    runs = unpriced = 0
    seen: set[str] = set()
    catalog: Mapping[str, Any] | None = None
    catalog_loaded = False
    for attempt_file in sorted((sessions_dir / session_id / "attempts").glob("*/attempt.json")):
        attempt = _read(attempt_file)
        run_dir = attempt.get("run_dir") if isinstance(attempt, dict) else None
        if not run_dir or run_dir in seen:
            continue
        seen.add(run_dir)
        usage = _read(Path(run_dir) / LLM_USAGE_ARTIFACT)
        if not isinstance(usage, dict) or not isinstance(usage.get("totals"), dict):
            continue
        run_totals = usage["totals"]
        runs += 1
        for key in _TOKEN_KEYS:
            try:
                totals[key] += max(0, int(run_totals.get(key) or 0))
            except (TypeError, ValueError):
                pass
        if str(usage.get("provider") or "").strip().lower() == "openrouter" and not catalog_loaded:
            catalog_loaded = True
            catalog = (load_catalog or (lambda: load_openrouter_catalog(sessions_dir.parent / "cache")))()
        price = run_price(usage, catalog)
        run_cost = usage_cost(price, run_totals) if price is not None else None
        if run_cost is None:
            unpriced += 1
        else:
            cost = (cost or 0.0) + run_cost
    return {
        **totals,
        "total_tokens": totals["input_tokens"] + totals["output_tokens"],
        "cost_usd": round(cost, 6) if cost is not None else None,
        "runs": runs,
        "unpriced_runs": unpriced,
    }
