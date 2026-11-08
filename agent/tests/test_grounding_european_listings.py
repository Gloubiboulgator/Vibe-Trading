"""European listings (CW8.PA, SAP.DE, NESN.SW) are known to the grounding identity layer.

The identity layer listed no European venue, so ``_infer_currency("CW8.PA")`` was None
and the evidence for a Paris ETF carried no currency. A close written "692,30 €" is a
EUR-marked figure and is compared only against EUR evidence, so an exact close was cut
to "(omitted※)": every price of a live PEA ETF table was lost this way (2026-11-08).

The suffixes are matched in uppercase only: ``.de``, ``.co``, ``.br``, ``.pa`` are also
web domains, and a source URL must not read as a ticker (as ``us.reuters`` once did).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger
from src.agent.grounding.identity import _infer_currency, _infer_venue, _scan_symbols

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("symbol", "currency"),
    [
        ("CW8.PA", "EUR"),
        ("MC.PA", "EUR"),
        ("SAP.DE", "EUR"),
        ("ASML.AS", "EUR"),
        ("ABI.BR", "EUR"),
        ("ENI.MI", "EUR"),
        ("SAN.MC", "EUR"),
        ("EDP.LS", "EUR"),
        ("RYA.IR", "EUR"),
        ("NOKIA.HE", "EUR"),
        ("OMV.VI", "EUR"),
        ("NESN.SW", "CHF"),
        ("VOLV-B.ST", "SEK"),
        ("NOVO-B.CO", "DKK"),
        ("EQNR.OL", "NOK"),
    ],
)
def test_european_listings_have_a_venue_and_a_currency(symbol: str, currency: str) -> None:
    assert _scan_symbols(f"{symbol} a clôturé hier.") == {symbol}
    assert _infer_venue(symbol) is not None
    assert _infer_currency(symbol) == currency


@pytest.mark.parametrize(
    "text",
    [
        "Source : https://www.boerse-frankfurt.de/etf",
        "voir site.co et exemple.br",
        "Données sur boursorama.pa ou finanzen.de",
    ],
)
def test_lowercase_web_domains_are_not_read_as_tickers(text: str) -> None:
    assert _scan_symbols(text) == set()


def _ledger(tmp_path: Path, symbol: str, close: float) -> GroundingLedger:
    ledger = GroundingLedger(run_dir=tmp_path, user_message="cours")
    ledger.ingest_tool_result(
        tool_name="get_market_data",
        arguments={"codes": [symbol]},
        result=json.dumps(
            {
                symbol: [
                    {
                        "trade_date": "2026-11-06T00:00:00",
                        "open": close * 0.99,
                        "high": close * 1.001,
                        "low": close * 0.98,
                        "close": close,
                        "volume": 11736,
                    }
                ]
            }
        ),
        call_id="prices",
        success=True,
    )
    return ledger


@pytest.mark.parametrize(
    ("symbol", "close", "prose"),
    [
        ("CW8.PA", 692.3, "CW8.PA a clôturé à 692,30 € le 06/11/2026."),
        ("CW8.PA", 692.3, "| ETF | Prix au 06/11/2026 |\n|---|---|\n| CW8.PA (MSCI World) | 692,30 € |"),
        ("SAP.DE", 210.75, "SAP.DE closed at 210.75 EUR."),
        ("NESN.SW", 81.4, "NESN.SW closed at CHF 81.40."),
        ("VOLV-B.ST", 250.4, "VOLV-B.ST closed at 250.40 SEK."),
    ],
)
def test_an_exact_european_close_in_its_currency_survives(
    tmp_path: Path, symbol: str, close: float, prose: str
) -> None:
    result = _ledger(tmp_path, symbol, close).validate_final_answer(prose)
    assert result.valid is True, result.issues


def test_a_wrong_european_close_is_still_rejected(tmp_path: Path) -> None:
    result = _ledger(tmp_path, "CW8.PA", 692.3).validate_final_answer(
        "CW8.PA a clôturé à 712,30 € le 06/11/2026."
    )
    assert result.valid is False
    assert "712,30" in [issue.get("claim") for issue in result.issues]


def test_a_european_close_in_the_wrong_currency_is_rejected(tmp_path: Path) -> None:
    result = _ledger(tmp_path, "CW8.PA", 692.3).validate_final_answer(
        "CW8.PA a clôturé à 692,30 USD."
    )
    assert result.valid is False
