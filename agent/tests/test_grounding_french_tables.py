"""An ETF found by ISIN, quoted in a French table (2026-11-14). Made-up values.

The ISIN search also returned a relay line whose ticker is the ISIN itself; it
was locked over the Paris line. The French table then wrote "| 10 nov |" in
its date column and "0,66 M" under "Volume": the month word bound no trade
date, and volumes were never among the price records. A year after a month
word ("juillet 2018") under a "Plus haut" column read as a price.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger
from src.agent.grounding.evidence import _timestamp_matches_claim_date

pytestmark = pytest.mark.unit

ISIN = "XS0000000017"
NAME = "Fonds Exemple Monde UCITS ETF"
CANDIDATES = [
    {"symbol": f"{ISIN}.SG", "name": NAME, "market": "eu", "exchange": "STU", "source": "yahoo"},
    {"symbol": "FXMD.MI", "name": NAME, "market": "eu", "exchange": "MIL", "source": "yahoo"},
    {"symbol": "FXMD.PA", "name": NAME, "market": "eu", "exchange": "PAR", "source": "yahoo"},
]
ROWS = [
    {"trade_date": "2026-11-09", "open": 4.10, "high": 4.20, "low": 4.05, "close": 4.15, "volume": 812000},
    {"trade_date": "2026-11-10", "open": 4.15, "high": 4.25, "low": 4.12, "close": 4.213, "volume": 655000},
]


def _ledger(tmp_path: Path) -> GroundingLedger:
    ledger = GroundingLedger(run_dir=tmp_path, user_message=f"Que penser de l'ETF {ISIN} ?")
    payload = {"ok": True, "source": "symbol_search", "data": {"query": ISIN, "candidates": CANDIDATES}}
    ledger.ingest_tool_result(
        tool_name="search_symbol",
        arguments={"query": ISIN},
        result=json.dumps(payload),
        call_id="resolve",
        success=True,
    )
    market = {"FXMD.PA": ROWS, "_provenance": {"FXMD.PA": {"source": "yahoo"}}}
    ledger.ingest_tool_result(
        tool_name="get_market_data",
        arguments={"codes": ["FXMD.PA"]},
        result=json.dumps(market),
        call_id="prices",
        success=True,
    )
    return ledger


def test_an_isin_search_locks_the_home_listing_not_the_isin_relay(tmp_path: Path) -> None:
    record = next(r for r in _ledger(tmp_path).identity_summary()["records"] if r["query"] == ISIN)
    assert (record["status"], record["symbol"]) == ("locked", "FXMD.PA")


@pytest.mark.parametrize(
    ("claim", "matches"),
    [
        ("10 nov", True),
        ("10 nov.", True),
        ("10 novembre 2026", True),
        ("1er nov", False),
        ("Nov 10, 2026", True),
        ("10 nov 2025", False),
        ("11 nov", False),
        ("10 truc", False),
    ],
)
def test_a_month_word_date_matches_its_trading_day(claim: str, matches: bool) -> None:
    assert _timestamp_matches_claim_date("2026-11-10T00:00:00", claim) is matches


def _table(date: str, close: str, volume: str) -> str:
    return (
        "FXMD.PA (source : yahoo ; devise : EUR)\n\n"
        "| Date | Clôture | Volume |\n"
        "|------|---------|--------|\n"
        f"| {date} | {close} € | {volume} M |\n"
    )


def test_a_french_price_table_matches_its_close_and_rounded_volume(tmp_path: Path) -> None:
    result = _ledger(tmp_path).validate_final_answer(_table("10 nov", "4,21", "0,66"))
    assert result.valid is True, result.issues


def test_a_french_volume_of_another_day_is_still_refused(tmp_path: Path) -> None:
    result = _ledger(tmp_path).validate_final_answer(_table("10 nov", "4,21", "0,81"))
    assert result.valid is False
    assert "0,81" in {str(issue.get("value")).strip() for issue in result.issues}


def test_a_year_after_a_month_word_is_a_date_not_a_price(tmp_path: Path) -> None:
    draft = (
        "FXMD.PA (source : yahoo ; devise : EUR)\n\n"
        "| Période | Plus haut | Plus bas |\n"
        "|---------|-----------|----------|\n"
        "| novembre | 4,25 € (novembre 2026) | 4,05 € (nov. 2026) |\n"
    )
    result = _ledger(tmp_path).validate_final_answer(draft)
    assert result.valid is True, result.issues


def test_a_french_range_and_a_count_with_its_unit_are_declarations() -> None:
    from src.agent.grounding.figures import parse_figures_block

    block = parse_figures_block(
        "Texte.\n\n```figures\n4 à 5 % | derived | estimation | FXMD.PA\n"
        "2 mois | count | horizon\n2 mois | observed | x\n```"
    )
    assert [(d.value_text, d.role) for d in block.declarations] == [
        ("4%", "derived"), ("5%", "derived"), ("2", "count"),
    ]
    assert [raw for _, raw in block.malformed] == ["2 mois | observed | x"]
