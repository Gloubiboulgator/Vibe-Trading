"""What a run's provider-reported tokens cost, for the models whose price is known.

Prices are USD per million tokens, from Anthropic's published model prices
(2026-11). A cache write is billed at 1.25x the input price: the service marks
its prompt ``cache_control: ephemeral``, the 5-minute TTL. A model missing here
has no cost; its tokens are still counted, never priced by guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

_CACHE_WRITE_MULTIPLIER = 1.25


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens."""

    input: float
    output: float
    cache_read: float

    @property
    def cache_write(self) -> float:
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


def usage_cost(model: str | None, totals: Mapping[str, Any]) -> float | None:
    """USD cost of one run's usage totals, or None for a model without a price.

    ``input_tokens`` as recorded includes the cached tokens, read and written;
    each part is billed at its own rate.
    """
    price = model_price(model)
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
