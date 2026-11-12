"""A portfolio review from a broker statement (2026-11-12).

The answer quoted an uploaded securities statement and ten instruments'
weekly closes, wrote its figures the French way, and lost four of them to
redaction after two refused drafts:

* "6 947,80 €" from the statement: its amounts are bare under a single
  "en €" header, so they had no currency and a euro claim could not match.
* "235,35" with ref "SU.PA": the ref was read as the tail of a portfolio
  tool's field "data.inputs.weights.SU.PA" and hid the instrument's closes.
* "64,33 %" noted "100 − 35,67": the 100 had no observation. A share
  written with "%" in the document now makes the complement a points
  figure; the statement's own weights carry no "%" on their cells, so that
  one stays refused, as the upstream unit rules want.
* "+22,4 %" noted "(25.26 − 20.63) / 20.63" over a ten-symbol call whose
  prose named the company, not the ticker: no symbol, so no anchor.

All values here are made up.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger
from src.agent.grounding.evidence import EvidenceRecord

pytestmark = pytest.mark.unit

STATEMENT = (
    "Relevé de titres au 30/09/2026\n"
    "Valeur Quantité Cours Valorisation\n"
    "en € en %\n"
    "ALPHA SA FR0000000001 10 50,00 30/09/26 500,00 40,00\n"
    "BETA SA FR0000000002 5 150,00 30/09/26 750,00 60,00\n"
    "Total portefeuille 1 250,00\n"
    "Droits de garde : 3,95 € par ligne\n"
)


def _close(symbol: str, value: float, day: str, call_id: str = "md-1") -> EvidenceRecord:
    return EvidenceRecord(
        call_id=call_id, tool="get_market_data", symbol=symbol, source="yahoo",
        timestamp=f"{day}T00:00:00", field="close", value=value, status="observed",
        currency="EUR", venue="euronext_paris", currency_conversion="none",
    )


def _ledger(tmp_path: Path, statement: str = STATEMENT) -> GroundingLedger:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    document = uploads / "releve.pdf"
    document.write_text(statement, encoding="utf-8")
    ledger = GroundingLedger(run_dir=tmp_path / "run", user_message="Que penses-tu de mon portefeuille ?")
    ledger.ingest_tool_result(
        tool_name="read_document",
        arguments={"file_path": str(document)},
        result=json.dumps({"status": "ok", "file": document.name, "format": "pdf", "text": statement}),
        call_id="doc-1",
        success=True,
    )
    ledger._evidence += [
        _close("AAA.PA", 41.20, "2026-09-29"),
        _close("AAA.PA", 50.45, "2026-11-10"),
        _close("BBB.PA", 302.00, "2026-09-29"),
        _close("BBB.PA", 234.80, "2026-11-10"),
        EvidenceRecord(
            call_id="xray-1", tool="portfolio_risk_xray", symbol=None, source="portfolio",
            timestamp=None, field="data.inputs.weights.BBB.PA", value=750.0, status="observed",
        ),
    ]
    ledger._session_symbols |= {"AAA.PA", "BBB.PA"}
    return ledger


def _issues(ledger: GroundingLedger, sentence: str, *lines: str) -> list[dict]:
    answer = f"{sentence}\n\n```figures\n" + "\n".join(lines) + "\n```\n"
    return list(ledger.validate_final_answer(answer).issues)


def test_a_statement_amount_takes_the_statement_s_only_currency(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Le relevé valorise AAA.PA et BBB.PA (Yahoo, EUR) à 1 250,00 € au 30/09.",
        "1 250,00 | observed | total du relevé | read_document",
    )
    assert issues == []


def test_a_statement_in_two_currencies_does_not_give_one(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path, STATEMENT + "Compte espèces en USD\n"),
        "Le relevé valorise AAA.PA et BBB.PA (Yahoo, EUR) à 1 250,00 € au 30/09.",
        "1 250,00 | observed | total du relevé | read_document",
    )
    assert issues


def test_a_symbol_ref_reads_that_instrument_not_a_field_named_after_it(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "BBB.PA (Yahoo) a clôturé à 234,80 € le 10/11/2026.",
        "234,80 | observed | BBB.PA clôture 2026-11-10 | BBB.PA",
    )
    assert issues == []


def test_a_difference_of_percentages_is_in_points(tmp_path) -> None:
    ledger = _ledger(tmp_path, STATEMENT + "Part des actions françaises : 37,50 %\n")
    issues = _issues(
        ledger,
        "Hors actions françaises, le reste pèse 62,50 % du portefeuille (relevé ; cours AAA.PA et BBB.PA, Yahoo, EUR).",
        "62,50 % | derived | 100 − 37,50 | read_document",
    )
    assert issues == []
    wrong = _issues(
        ledger,
        "Hors actions françaises, le reste pèse 72,50 % du portefeuille (relevé ; cours AAA.PA et BBB.PA, Yahoo, EUR).",
        "72,50 % | derived | 100 − 37,50 | read_document",
    )
    assert [issue["reason"] for issue in wrong] == ["derivation_result_mismatch"]


def test_a_formula_belongs_to_the_one_instrument_that_printed_its_operands(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Depuis le relevé, l'action Alpha a progressé de 22,5 % (cours AAA.PA et BBB.PA, Yahoo, EUR).",
        "22,5 % | derived | (50.45 − 41.20) / 41.20 | get_market_data",
    )
    assert issues == []
