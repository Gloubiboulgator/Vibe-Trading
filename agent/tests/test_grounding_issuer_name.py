"""A company name resolves to the company, not a token named after it (2026-11-12).

"Je veux souscrire à l'IPO Anthropic" searched "Anthropic". The resolver
answered ANT.US "Anthropic PBC-A", a SEC registrant, and Yahoo's crypto
ANTHROPIC-USD, a tokenized stand-in. The crypto's ticker spelled the query
exactly, so it was locked, and the filings and news calls on ANT.US were
refused as an identity mismatch. The candidates are the resolver's answers
from that run, shortened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger

pytestmark = pytest.mark.unit

ANTHROPIC = [
    {"symbol": "ANT.US", "name": "Anthropic PBC-A", "market": "us", "source": "eastmoney", "cik": "0002130357"},
    {"symbol": "ANTW.US", "name": "Anthropic AI Lab Ecosystem ETF", "market": "us",
     "source": "eastmoney", "also_from": ["yahoo"]},
    {"symbol": "ANTHROPIC-USD", "name": "Anthropic tokenized stock (PreStocks) USD", "market": "global",
     "type": "cryptocurrency", "exchange": "CCC", "source": "yahoo"},
    {"symbol": "ANTHZZX.US", "name": "Anthropic - Company Level", "market": "us",
     "type": "mutualfund", "exchange": "NAS", "source": "yahoo"},
    {"symbol": "CLAU.VI", "name": "21shares Anthropic Synth. ETP", "market": "eu",
     "type": "equity", "exchange": "VIE", "source": "yahoo"},
]


def _status(tmp_path: Path, query: str, candidates: list[dict]) -> tuple[str, str | None]:
    ledger = GroundingLedger(run_dir=tmp_path, user_message="Je veux souscrire à l'IPO.")
    payload = {"ok": True, "source": "symbol_search", "data": {"query": query, "candidates": candidates}}
    ledger.ingest_tool_result(
        tool_name="search_symbol",
        arguments={"query": query},
        result=json.dumps(payload, ensure_ascii=False),
        call_id=f"resolve-{query}",
        success=True,
    )
    record = next(r for r in ledger.identity_summary()["records"] if r["query"] == query)
    return record["status"], record["symbol"]


def test_the_registrant_named_as_the_query_wins_over_a_token(tmp_path) -> None:
    assert _status(tmp_path, "Anthropic", ANTHROPIC) == ("locked", "ANT.US")


def test_a_registrant_with_another_name_does_not_win(tmp_path) -> None:
    candidates = [
        {"symbol": "ACME-USD", "name": "Acme token USD", "market": "global",
         "type": "cryptocurrency", "exchange": "CCC", "source": "yahoo"},
        {"symbol": "ACMR.US", "name": "ACM Research Inc", "market": "us", "source": "yahoo", "cik": "0001680062"},
    ]
    assert _status(tmp_path, "Acme", candidates) == ("locked", "ACME-USD")
