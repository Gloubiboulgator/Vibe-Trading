"""A currency-marked EPS quoted from get_stock_profile is grounded (2026-11-08).

"bénéfice futur de 9.3662 € par action" was refused as absent from the
get_stock_profile call that returned ``"forwardEps": 9.3662``: a figure written
with its currency only consults money evidence, and EPS was not money.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger

pytestmark = pytest.mark.unit

PROFILE = {
    "ok": True,
    "ticker": "NEX.PA",
    "data": {
        "listing": {"symbol": "NEX.PA", "currency": "EUR"},
        "sections": {"key_stats": {"forwardPE": 13.18571, "trailingEps": -0.9, "forwardEps": 9.3662, "beta": 1.007}},
    },
}


def _answer(eps: str) -> str:
    return (
        f"Le BPA attendu de Nexans est de {eps} € par action.\n\n"
        "```figures\n"
        f"{eps} | observed | forwardEps Nexans | profile-1\n"
        "```\n"
    )


def _ledger(tmp_path: Path) -> GroundingLedger:
    ledger = GroundingLedger(run_dir=tmp_path, user_message="Analyse Nexans pour mon PEA")
    ledger.ingest_tool_result(
        tool_name="get_stock_profile",
        arguments={"ticker": "NEX.PA"},
        result=json.dumps(PROFILE),
        call_id="profile-1",
        success=True,
    )
    return ledger


def test_the_returned_eps_is_grounded(tmp_path) -> None:
    assert _ledger(tmp_path).validate_final_answer(_answer("9.3662")).issues == []


def test_an_eps_the_call_did_not_return_is_still_refused(tmp_path) -> None:
    issues = _ledger(tmp_path).validate_final_answer(_answer("9.9662")).issues
    assert issues


def _beta_answer() -> str:
    return (
        "Le bêta de Nexans (NEX.PA) est de 1.007.\n\n"
        "```figures\n"
        "1.007 | observed | beta NEX.PA | get_stock_profile::data.sections.key_stats.beta\n"
        "```\n"
    )


def test_a_tool_field_ref_with_one_call_for_the_symbol_is_accepted(tmp_path) -> None:
    assert _ledger(tmp_path).validate_final_answer(_beta_answer()).issues == []


def test_a_tool_field_ref_with_two_calls_for_the_symbol_still_fails_closed(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    second = json.loads(json.dumps(PROFILE))
    second["data"]["sections"]["key_stats"]["beta"] = 1.2
    ledger.ingest_tool_result(
        tool_name="get_stock_profile",
        arguments={"ticker": "NEX.PA"},
        result=json.dumps(second),
        call_id="profile-2",
        success=True,
    )
    reasons = {issue["reason"] for issue in ledger.validate_final_answer(_beta_answer()).issues}
    assert reasons == {"field_ref_needs_call_id"}


def test_a_tool_and_symbol_ref_reads_that_symbols_calls(tmp_path) -> None:
    answer = (
        "Le PER attendu de Nexans est de 13.19.\n\n"
        "```figures\n"
        "13.19 | observed | forwardPE Nexans | get_stock_profile NEX.PA\n"
        "```\n"
    )
    assert _ledger(tmp_path).validate_final_answer(answer).issues == []
    wrong = answer.replace("13.19", "18.6")
    assert _ledger(tmp_path).validate_final_answer(wrong).issues
