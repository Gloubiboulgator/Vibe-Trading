"""A follow-up message keeps the instruments the session already resolved (2026-11-10).

A user asked about ASML on 9 November; the resolver locked ``ASML.AS``. The next
day "ASML a énormément monté..." started from an empty identity state, so the
model's ``get_market_data("ASML.AS")`` and ``technical_indicators`` were refused
with ``identity_required`` and it had to resolve the name again.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger
from src.agent.grounding.ledger import GROUNDING_ARTIFACT, load_prior_identities

pytestmark = pytest.mark.unit

ASML = {
    "query": "ASML",
    "status": "locked",
    "symbol": "ASML.AS",
    "venue": "AMS",
    "instrument_type": "listed_security",
    "currency": "EUR",
    "source_tool_call_id": "toolu_prior",
    "source": ["yahoo"],
    "candidates": [{"symbol": "ASML.AS", "name": "ASML HOLDING", "market": "eu"}],
}


def _ledger(message: str, prior: list[dict], **kwargs) -> GroundingLedger:
    return GroundingLedger(
        run_dir=Path(tempfile.mkdtemp()), user_message=message, prior_identities=prior, **kwargs
    )


def _allowed(ledger: GroundingLedger, symbol: str) -> bool:
    return ledger.authorize_tool_call(
        "get_market_data",
        {"codes": [symbol]},
        batch_authorized_symbols=ledger.authorized_symbols,
        batch_identity_status=ledger.identity_status,
        call_id="toolu_next",
    ).allowed


def test_the_follow_up_reuses_the_earlier_lock() -> None:
    ledger = _ledger("ASML a énormément monté et peu baissé. la baisse est-elle terminée ?", [ASML])
    assert ledger.authorized_symbols == {"ASML.AS"}
    assert _allowed(ledger, "ASML.AS")
    assert not _allowed(ledger, "ASML.US")


def test_without_an_earlier_lock_the_gate_still_asks_for_a_resolution() -> None:
    assert not _allowed(_ledger("ASML a énormément monté.", []), "ASML.AS")


def test_a_message_asking_for_the_us_listing_drops_the_lock() -> None:
    ledger = _ledger("Et la cotation américaine d'ASML ?", [ASML])
    assert ledger.authorized_symbols == set()


def test_pea_mode_drops_a_us_lock() -> None:
    sap_us = {**ASML, "query": "SAP", "symbol": "SAP.US", "venue": "NYSE", "currency": "USD"}
    ledger = _ledger(
        "Et SAP ?", [sap_us, ASML], standing_markets=(("eu", "session:pea_mode"),)
    )
    assert ledger.authorized_symbols == {"ASML.AS"}


def test_the_latest_turn_wins_and_unlocked_records_are_ignored() -> None:
    older = {**ASML, "symbol": "ASML.US"}
    ambiguous = {**ASML, "query": "Novo Nordisk", "status": "ambiguous", "symbol": None}
    ledger = _ledger("Et ASML ?", [older, ASML, ambiguous])
    assert ledger.authorized_symbols == {"ASML.AS"}


def test_earlier_runs_are_read_in_order(tmp_path: Path) -> None:
    runs = []
    for index, symbol in enumerate(("ASML.US", "ASML.AS")):
        run = tmp_path / f"run{index}"
        (run / "artifacts").mkdir(parents=True)
        payload = {"identity": {"records": [{**ASML, "symbol": symbol}]}}
        (run / "artifacts" / GROUNDING_ARTIFACT).write_text(json.dumps(payload), encoding="utf-8")
        runs.append(run)
    runs.append(tmp_path / "missing")
    assert [record["symbol"] for record in load_prior_identities(runs)] == ["ASML.US", "ASML.AS"]


def test_a_fresh_resolution_replaces_a_carried_lock() -> None:
    sap_us = {**ASML, "query": "SAP", "symbol": "SAP.US", "venue": "NYSE", "currency": "USD"}
    ledger = _ledger("Et SAP ?", [sap_us])
    ledger.authorize_tool_call(
        "search_symbol", {"query": "SAP"}, batch_authorized_symbols=set(), call_id="toolu_search"
    )
    ledger.ingest_tool_result(
        tool_name="search_symbol",
        arguments={"query": "SAP"},
        result=json.dumps(
            {
                "ok": True,
                "data": {
                    "query": "SAP",
                    "candidates": [
                        {"symbol": "SAP.DE", "name": "SAP SE", "market": "eu", "exchange": "GER", "source": "yahoo"}
                    ],
                },
            }
        ),
        call_id="toolu_search",
        success=True,
    )
    assert ledger.identity_status == "locked"
    assert ledger.authorized_symbols == {"SAP.DE"}
