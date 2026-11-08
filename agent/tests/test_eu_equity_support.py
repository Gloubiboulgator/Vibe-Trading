"""Euro-area listings route to a EUR market served by Yahoo (2026-11-08).

AI.PA / DG.PA matched no market pattern, defaulted to ``a_share`` and were
fetched from tencent / eastmoney / akshare only, so technical_indicators
answered "No data returned" for every Paris listing.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.engines._market_hooks import _MARKET_CURRENCY, _detect_market, _detect_submarket
from backtest.engines.global_equity import GlobalEquityEngine
from backtest.loaders.base import declared_currency_required, normalize_declared_quote_currency
from backtest.loaders.registry import FALLBACK_CHAINS
from src.agent.resolution_context import candidate_market
from src.market_data import detect_source

pytestmark = pytest.mark.unit

EURO_AREA = ["AI.PA", "DG.PA", "ASML.AS", "ABI.BR", "EDP.LS", "ENEL.MI", "SAN.MC", "SAP.DE", "AIL.F", "NOKIA.HE"]


@pytest.mark.parametrize("symbol", EURO_AREA)
def test_euro_area_symbols_route_to_yahoo_in_eur(symbol: str) -> None:
    assert _detect_market(symbol) == "eu_equity"
    assert _MARKET_CURRENCY["eu_equity"] == "EUR"
    assert detect_source(symbol) == "yahoo"
    assert _detect_submarket([symbol]) == "eu"
    assert candidate_market({"symbol": symbol}) == "eu"


def test_the_chain_is_yahoo_first() -> None:
    assert FALLBACK_CHAINS["eu_equity"][:2] == ["yahoo", "yfinance"]


@pytest.mark.parametrize("symbol", ["BN.SW", "VOD.L", "AAPL.US", "600519.SH", "ESZ4"])
def test_other_markets_are_untouched(symbol: str) -> None:
    assert _detect_market(symbol) != "eu_equity"


def test_a_non_eur_line_is_refused() -> None:
    frame = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1]})
    assert declared_currency_required("AI.PA")
    assert normalize_declared_quote_currency(frame, "AI.PA", "EUR").attrs["quote_currency"] == "EUR"
    with pytest.raises(ValueError):
        normalize_declared_quote_currency(frame, "IWDA.AS", "USD")


def test_engine_uses_whole_shares_and_the_configured_rate() -> None:
    engine = GlobalEquityEngine({"eu_commission": 0.001, "slippage_eu": 0.002}, market="eu")
    assert engine.round_size(10.7, 50.0) == 10.0
    assert engine.calc_commission(10, 50.0, 1, True) == pytest.approx(0.5)
    assert engine.apply_slippage(100.0, 1) == pytest.approx(100.2)


@pytest.mark.parametrize("symbol", ["CRL.MI", "AI.PA", "SAP.DE"])
def test_financial_statements_accept_euro_area_listings(symbol: str) -> None:
    from src.tools.financial_statements_tool import _classify_market

    assert _classify_market(symbol) == "eu"
