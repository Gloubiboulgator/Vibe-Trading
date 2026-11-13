"""What a run's provider-reported tokens cost, for the models whose price is known.

Anthropic prices are USD per million tokens, from Anthropic's published model
prices (2026-11). A cache write is billed at 1.25x the input price: the service
marks its prompt ``cache_control: ephemeral``, the 5-minute TTL.

OpenRouter prices come from its public model catalog, kept a day on disk; a
model priced by time of day is priced at the hour its run ended.

A model with no known price has no cost; its tokens are still counted, never
priced by guess.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_OPENROUTER_CACHE_FILE = "openrouter_pricing.json"
_OPENROUTER_CACHE_SECONDS = 24 * 3600
_OPENROUTER_RETRY_SECONDS = 15 * 60

_CACHE_WRITE_MULTIPLIER = 1.25


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens."""

    input: float
    output: float
    cache_read: float
    cache_write_price: float | None = None

    @property
    def cache_write(self) -> float:
        if self.cache_write_price is not None:
            return self.cache_write_price
        return self.input * _CACHE_WRITE_MULTIPLIER


# Exact model ids, matched after stripping a provider prefix ("anthropic/").
_PRICES: dict[str, ModelPrice] = {
    "claude-fable-5-2": ModelPrice(input=8.0, output=40.0, cache_read=0.20),
    "claude-fable-5-1": ModelPrice(input=10.0, output=50.0, cache_read=0.25),
    "claude-fable-5": ModelPrice(input=10.0, output=50.0, cache_read=1.0),
    "claude-opus-5-5": ModelPrice(input=4.0, output=20.0, cache_read=0.20),
    "claude-opus-5": ModelPrice(input=5.0, output=25.0, cache_read=0.50),
    "claude-sonnet-5-5": ModelPrice(input=2.0, output=10.0, cache_read=0.10),
}


def model_price(model: str | None) -> ModelPrice | None:
    """The price of a model id, or None when it is not known."""
    if not model:
        return None
    name = model.strip().lower().rsplit("/", 1)[-1]
    return _PRICES.get(name)


def _count(totals: Mapping[str, Any], key: str) -> int:
    try:
        return max(0, int(totals.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def _per_million(value: Any) -> float | None:
    """An OpenRouter per-token price string as USD per million tokens."""
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price * 1_000_000 if price >= 0 else None


def _active_override(pricing: Mapping[str, Any], at: datetime | None) -> Mapping[str, Any]:
    """The time-of-day override in force at ``at`` (UTC), else the base price.

    ``utc_start`` / ``utc_end`` are HHMM; an end at or before the start wraps
    past midnight; an override without hours covers its whole days.
    """
    overrides = pricing.get("overrides")
    if at is None or not isinstance(overrides, list):
        return pricing
    day = at.strftime("%A").lower()
    hhmm = at.hour * 100 + at.minute
    for override in overrides:
        if not isinstance(override, dict) or day not in (override.get("utc_days") or []):
            continue
        start, end = override.get("utc_start"), override.get("utc_end")
        if start is None or end is None:
            return override
        inside = start <= hhmm < end if start < end else (hhmm >= start or hhmm < end)
        if inside:
            return override
    return pricing


def openrouter_price(
    catalog: Mapping[str, Mapping[str, Any]] | None, model: str | None, at: datetime | None = None
) -> ModelPrice | None:
    """The price of an OpenRouter model id from its catalog, or None."""
    if not catalog or not model:
        return None
    pricing = catalog.get(model.strip())
    if not isinstance(pricing, Mapping):
        return None
    active = _active_override(pricing, at)
    prompt = _per_million(active.get("prompt", pricing.get("prompt")))
    completion = _per_million(active.get("completion", pricing.get("completion")))
    if prompt is None or completion is None:
        return None
    cache_read = _per_million(active.get("input_cache_read", pricing.get("input_cache_read")))
    cache_write = _per_million(active.get("input_cache_write", pricing.get("input_cache_write")))
    return ModelPrice(
        input=prompt,
        output=completion,
        cache_read=prompt if cache_read is None else cache_read,
        cache_write_price=prompt if cache_write is None else cache_write,
    )


def _fetch_openrouter_catalog() -> dict[str, Any]:
    import httpx

    response = httpx.get(OPENROUTER_MODELS_URL, timeout=8.0, headers={"Accept": "application/json"})
    response.raise_for_status()
    return {
        str(item["id"]): item["pricing"]
        for item in response.json().get("data", [])
        if isinstance(item, dict) and item.get("id") and isinstance(item.get("pricing"), dict)
    }


def load_openrouter_catalog(
    cache_dir: Path,
    *,
    fetch: Callable[[], dict[str, Any]] = _fetch_openrouter_catalog,
    now: Callable[[], float] = time.time,
) -> dict[str, Any] | None:
    """OpenRouter prices by model id, from a copy at most a day old.

    A failed fetch keeps the stale copy and is retried after 15 minutes, so
    an offline service neither loses its prices nor calls on every request.
    """
    path = cache_dir / _OPENROUTER_CACHE_FILE
    cached: dict[str, Any] | None = None
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cached = None
    if isinstance(cached, dict):
        age = now() - float(cached.get("fetched_at") or 0)
        retry_after = float(cached.get("failed_at") or 0)
        if age < _OPENROUTER_CACHE_SECONDS or now() - retry_after < _OPENROUTER_RETRY_SECONDS:
            return cached.get("models") or None
    try:
        models = fetch()
        record = {"fetched_at": now(), "models": models}
    except Exception as exc:  # noqa: BLE001 - a missing price must not break the bar
        logger.info("OpenRouter price catalog unavailable: %s", exc)
        models = (cached or {}).get("models") or {}
        record = {**(cached or {}), "models": models, "failed_at": now()}
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.debug("OpenRouter price cache write skipped: %s", exc)
    return models or None


def _run_time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def run_price(
    usage: Mapping[str, Any], openrouter_catalog: Mapping[str, Mapping[str, Any]] | None = None
) -> ModelPrice | None:
    """The price that applies to one run's ``llm_usage.json``."""
    model = usage.get("model")
    if str(usage.get("provider") or "").strip().lower() == "openrouter":
        return openrouter_price(openrouter_catalog, model, _run_time(usage.get("updated_at")))
    return model_price(model)


def usage_cost(model: str | None | ModelPrice, totals: Mapping[str, Any]) -> float | None:
    """USD cost of one run's usage totals, or None for a model without a price.

    ``model`` is an Anthropic model id or an already resolved price.
    ``input_tokens`` as recorded includes the cached tokens, read and written;
    each part is billed at its own rate.
    """
    price = model if isinstance(model, ModelPrice) else model_price(model)
    if price is None:
        return None
    cache_read = _count(totals, "cache_read_tokens")
    cache_write = _count(totals, "cache_creation_tokens")
    uncached = max(0, _count(totals, "input_tokens") - cache_read - cache_write)
    output = _count(totals, "output_tokens")
    return (
        uncached * price.input
        + cache_read * price.cache_read
        + cache_write * price.cache_write
        + output * price.output
    ) / 1_000_000
