"""Consensus EPS from get_stock_profile's earnings_trend is grounded (2026-11-11).

An ASML answer wrote "41,41393 €" of 2026 EPS citing
``data.sections.earnings_trend[2].eps_avg``, the exact field that held it, and
the figure was omitted: a figure written with its currency only consults money
evidence, and the earnings_trend EPS leaves were not money. The draft before
had rounded figures and refs like ``get_stock_profile::earnings_trend 0y
eps_avg``, refused with no hint, so the model fell back to raw values.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger

pytestmark = pytest.mark.unit

PROFILE = {
    "ok": True,
    "ticker": "ASML.AS",
    "data": {
        "listing": {"symbol": "ASML.AS", "currency": "EUR"},
        "sections": {
            "key_stats": {"currentPrice": 1403.8, "forwardEps": 56.43418},
            "earnings_trend": [
                {"period": "0y", "eps_avg": 41.41393, "eps_trend_30d_ago": 38.34441},
                {"period": "+1y", "eps_avg": 56.43418, "eps_trend_30d_ago": 51.73157},
            ],
        },
    },
}


def _ledger(tmp_path: Path) -> GroundingLedger:
    ledger = GroundingLedger(run_dir=tmp_path, user_message="ASML peut encore monter ?")
    ledger.ingest_tool_result(
        tool_name="get_stock_profile",
        arguments={"ticker": "ASML.AS"},
        result=json.dumps(PROFILE),
        call_id="profile-1",
        success=True,
    )
    return ledger


def _answer(value: str, ref: str) -> str:
    return (
        f"Le BPA moyen attendu d'ASML (ASML.AS) pour 2026 est de {value} €. "
        "Le cours est de 1 403,8 €.\n\n"
        "```figures\n"
        f"{value.replace(',', '.')} | observed | BPA 2026e | {ref}\n"
        "1403.8 | observed | cours | data.sections.key_stats.currentPrice\n"
        "```\n"
    )


@pytest.mark.parametrize("value", ["41,41393", "41,41"])
def test_a_consensus_eps_with_its_currency_is_grounded(tmp_path, value) -> None:
    answer = _answer(value, "data.sections.earnings_trend[0].eps_avg")
    assert _ledger(tmp_path).validate_final_answer(answer).issues == []


def test_another_period_s_eps_is_still_refused(tmp_path) -> None:
    answer = _answer("56,43", "data.sections.earnings_trend[0].eps_avg")
    assert _ledger(tmp_path).validate_final_answer(answer).issues


def test_a_described_field_ref_gets_the_exact_ref_as_a_hint(tmp_path) -> None:
    answer = _answer("41,41", "get_stock_profile::earnings_trend 0y eps_avg")
    [issue] = _ledger(tmp_path).validate_final_answer(answer).issues
    assert issue["reason"] == "not_in_referenced_call"
    assert issue["field_ref_candidates"] == ["profile-1::data.sections.earnings_trend[0].eps_avg"]


def test_a_hint_never_names_a_field_the_ref_did_not_spell(tmp_path) -> None:
    # 56,43 is also forwardEps, but the ref spelled eps_avg.
    answer = _answer("56,43", "get_stock_profile::earnings_trend +1y eps_avg")
    [issue] = _ledger(tmp_path).validate_final_answer(answer).issues
    assert issue["field_ref_candidates"] == ["profile-1::data.sections.earnings_trend[1].eps_avg"]
