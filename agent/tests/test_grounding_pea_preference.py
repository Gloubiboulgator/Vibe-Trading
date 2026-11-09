"""A PEA conversation prefers euro-area listings when locking a name (2026-11-08).

"Sanofi" locked the SNY.US ADR (an exact name tie broken by its SEC CIK), and
"Danone" stayed ambiguous between BN.PA and two US OTC lines, so every
indicator call on SAN.PA / BN.PA in a PEA portfolio run was refused. The
candidate lists below are the resolver's answers from that run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.grounding import GroundingLedger

pytestmark = pytest.mark.unit

SANOFI = [
    {"symbol": "SNY.US", "name": "Sanofi", "market": "us", "type": "equity", "exchange": "NMS", "source": "yahoo", "cik": "0001121404"},
    {"symbol": "SAN.PA", "name": "SANOFI", "market": "global", "type": "equity", "exchange": "PAR", "source": "yahoo"},
    {"symbol": "SANOFI.NS", "name": "SANOFI INDIA LIMITED", "market": "in", "type": "equity", "exchange": "NSI", "source": "yahoo"},
    {"symbol": "SNW.DE", "name": "Sanofi S.A.                   A", "market": "global", "type": "equity", "exchange": "GER", "source": "yahoo"},
]
DANONE = [
    {"symbol": "BN.PA", "name": "DANONE", "market": "global", "type": "equity", "exchange": "PAR", "source": "yahoo"},
    {"symbol": "DANOY.US", "name": "Danone", "market": "us", "type": "equity", "exchange": "OQX", "source": "yahoo"},
    {"symbol": "BN.SW", "name": "DANONE S.A. EO -,25", "market": "global", "type": "equity", "exchange": "EBS", "source": "yahoo"},
    {"symbol": "BSN.F", "name": "Danone S.A.                   A", "market": "global", "type": "equity", "exchange": "FRA", "source": "yahoo"},
    {"symbol": "GPDNF.US", "name": "Danone", "market": "us", "type": "equity", "exchange": "OQX", "source": "yahoo"},
]
SCHNEIDER = [
    {"symbol": "SU.PA", "name": "SCHNEIDER ELECTRIC SE", "market": "global", "type": "equity", "exchange": "PAR", "source": "yahoo"},
    {"symbol": "SBGSY.US", "name": "Schneider Electric SE", "market": "us", "type": "equity", "exchange": "PNK", "source": "yahoo"},
    {"symbol": "SND.DE", "name": "Schneider Electric SE         A", "market": "global", "type": "equity", "exchange": "GER", "source": "yahoo"},
]
ASML = [
    {"symbol": "ASML.US", "name": "阿斯麦", "market": "us", "type": "美股", "source": "eastmoney", "also_from": ["yahoo"], "cik": "0000937966"},
    {"symbol": "ASMH.US", "name": "ASML Holding NV ADRhedged", "market": "us", "type": "美股", "source": "eastmoney"},
    {"symbol": "ASML.AS", "name": "ASML HOLDING", "market": "global", "type": "equity", "exchange": "AMS", "source": "yahoo"},
]
NVIDIA = [
    {"symbol": "NVDA.US", "name": "英伟达", "market": "us", "type": "美股", "source": "eastmoney", "also_from": ["yahoo"], "cik": "0001045810"},
    {"symbol": "NVD.DE", "name": "NVIDIA Corp.", "market": "global", "type": "equity", "exchange": "GER", "source": "yahoo"},
]

PEA_START = "Je veux que tu me construises un portefeuille PEA à partir d'une feuille blanche."
FOLLOW_UP = "c'est idiot de prendre des actions à leur plus haut"


def _ledger(tmp_path: Path, message: str, history: list[dict[str, Any]] | None = None) -> GroundingLedger:
    return GroundingLedger(run_dir=tmp_path, user_message=message, history=history)


def _ingest(ledger: GroundingLedger, query: str, candidates: list[dict[str, Any]]) -> None:
    payload = {
        "ok": True,
        "source": "symbol_search",
        "data": {"query": query, "candidates": candidates, "sources": {"eastmoney": "ok", "yahoo": "ok"}},
    }
    ledger.ingest_tool_result(
        tool_name="search_symbol",
        arguments={"query": query},
        result=json.dumps(payload, ensure_ascii=False),
        call_id=f"resolve-{query}",
        success=True,
    )


def _status(ledger: GroundingLedger, query: str) -> tuple[str, str | None]:
    record = next(r for r in ledger.identity_summary()["records"] if r["query"] == query)
    return record["status"], record["symbol"]


@pytest.mark.parametrize(
    ("query", "candidates", "expected"),
    [("Sanofi", SANOFI, "SAN.PA"), ("Danone", DANONE, "BN.PA"), ("ASML", ASML, "ASML.AS")],
)
def test_a_pea_turn_locks_the_euro_area_listing(tmp_path, query, candidates, expected) -> None:
    ledger = _ledger(tmp_path, PEA_START)
    _ingest(ledger, query, candidates)
    assert _status(ledger, query) == ("locked", expected)


def test_the_pea_preference_holds_on_a_later_turn(tmp_path) -> None:
    ledger = _ledger(tmp_path, FOLLOW_UP, history=[{"role": "user", "content": PEA_START}])
    _ingest(ledger, "Sanofi", SANOFI)
    assert _status(ledger, "Sanofi") == ("locked", "SAN.PA")


def test_without_pea_the_choice_is_unchanged(tmp_path) -> None:
    ledger = _ledger(tmp_path, "Analyse Sanofi et Danone")
    _ingest(ledger, "Sanofi", SANOFI)
    _ingest(ledger, "Danone", DANONE)
    assert _status(ledger, "Sanofi") == ("locked", "SNY.US")
    assert _status(ledger, "Danone")[0] == "ambiguous"


def test_the_preference_needs_a_matching_euro_area_name(tmp_path) -> None:
    """Schneider matches up to its legal form (SU.PA, since 2026-11-09); Nvidia keeps its US line."""
    ledger = _ledger(tmp_path, PEA_START)
    _ingest(ledger, "Schneider Electric", SCHNEIDER)
    _ingest(ledger, "Nvidia", NVIDIA)
    assert _status(ledger, "Schneider Electric") == ("locked", "SU.PA")
    assert _status(ledger, "Nvidia") == ("locked", "NVDA.US")


def test_an_explicit_market_still_wins(tmp_path) -> None:
    ledger = _ledger(tmp_path, "Pour mon PEA, compare avec Sanofi en US stocks")
    _ingest(ledger, "Sanofi", SANOFI)
    assert _status(ledger, "Sanofi") == ("locked", "SNY.US")


def test_the_preference_is_audited_as_not_explicit(tmp_path) -> None:
    ledger = _ledger(tmp_path, PEA_START)
    _ingest(ledger, "Sanofi", SANOFI)
    record = ledger.identity_summary()["records"][0]
    assert record["resolution_constraints"][0]["value"] == "eu"
    assert record["resolution_constraints"][0]["explicit"] is False


KERING = [
    {"symbol": "KER.PA", "name": "KERING", "market": "eu", "type": "equity", "exchange": "PAR", "source": "yahoo"},
    {"symbol": "PPRUY.US", "name": "Kering SA", "market": "us", "type": "equity", "exchange": "PNK", "source": "yahoo"},
    {"symbol": "1KER.MI", "name": "KERING", "market": "eu", "type": "equity", "exchange": "MIL", "source": "yahoo"},
    {"symbol": "KER.VI", "name": "KERING SA", "market": "eu", "type": "equity", "exchange": "VIE", "source": "yahoo"},
]
STELLANTIS = [
    {"symbol": "STLA.US", "name": "Stellantis集团", "market": "us", "type": "美股", "source": "eastmoney"},
    {"symbol": "STLAM.MI", "name": "STELLANTIS", "market": "eu", "type": "equity", "exchange": "MIL", "source": "yahoo"},
    {"symbol": "STLAP.PA", "name": "STELLANTIS NV", "market": "eu", "type": "equity", "exchange": "PAR", "source": "yahoo"},
    {"symbol": "8TI.HM", "name": "Stellantis N.V.               A", "market": "eu", "type": "equity", "exchange": "HAM", "source": "yahoo"},
]
SARTORIUS = [
    {"symbol": "DIM.PA", "name": "SARTORIUS STED BIO", "market": "eu", "type": "equity", "exchange": "PAR", "source": "yahoo"},
    {"symbol": "DIMP.XD", "name": "Sartorius Stedim Biotech", "market": "global", "type": "equity", "exchange": "DXE", "source": "yahoo"},
    {"symbol": "4DIM.TI", "name": "SARTORIUS STEDIM BIOTECH", "market": "global", "type": "equity", "exchange": "TLO", "source": "yahoo"},
]
TWO_HOMES = [
    {"symbol": "XYZ.PA", "name": "XYZ", "market": "eu", "source": "yahoo"},
    {"symbol": "XYZB.PA", "name": "XYZ", "market": "eu", "source": "yahoo"},
]


@pytest.mark.parametrize(
    ("query", "candidates", "expected"),
    [
        ("Kering", KERING, "KER.PA"),
        ("Stellantis", STELLANTIS, "STLAP.PA"),
        ("Sartorius Stedim Biotech", SARTORIUS, "DIM.PA"),
        ("XYZ", TWO_HOMES, None),
    ],
)
def test_a_name_on_several_euro_venues_locks_its_home_listing(tmp_path: Path, query, candidates, expected) -> None:
    """2026-11-09: Kering, Sartorius and Forvia stayed ambiguous; Stellantis locked Milan."""
    ledger = _ledger(tmp_path, PEA_START)
    _ingest(ledger, query, candidates)
    status, symbol = _status(ledger, query)
    assert (symbol if status == "locked" else None) == expected

