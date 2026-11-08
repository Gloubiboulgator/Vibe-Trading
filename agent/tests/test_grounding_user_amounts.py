"""Amounts the user gave (a budget) are declared ``cited``, not ``count``.

A live PEA run ("J'ai 3000 euros") lost every "3 000 €" to "(omitted※)": the models
declared the user's budget ``count``, which may not carry a currency mark since a
price smuggled in as a count must be checked as observed. The gate already accepts
a ``cited`` amount whose source is visible on its line; the prompt and the
correction now say so, and these tests pin that the documented shape passes while
an unsourced amount still does not.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.context import _SYSTEM_PROMPT
from src.agent.grounding import GroundingLedger

pytestmark = pytest.mark.unit


def _ledger(tmp_path: Path) -> GroundingLedger:
    ledger = GroundingLedger(
        run_dir=tmp_path, user_message="Quelles actions acheter sur mon PEA ? J'ai 3000 euros"
    )
    ledger.ingest_tool_result(
        tool_name="get_market_data",
        arguments={"codes": ["AAPL.US"]},
        result=json.dumps(
            {
                "AAPL.US": [
                    {
                        "trade_date": "2026-11-06T00:00:00",
                        "open": 1350.0,
                        "high": 1370.0,
                        "low": 1340.0,
                        "close": 1362.5,
                        "volume": 1234567,
                    }
                ]
            }
        ),
        call_id="prices",
        success=True,
    )
    return ledger


def _figures(*rows: str) -> str:
    return "\n\n```figures\n" + "\n".join(rows) + "\n```"


def test_the_users_budget_and_its_split_pass_when_cited_on_their_line(tmp_path: Path) -> None:
    answer = (
        "Avec votre budget de 3 000 €, AAPL.US a clôturé à 1 362,50 USD.\n\n"
        "- Ligne 1 : 1 500 €, soit la moitié de votre budget.\n"
        "- Si votre budget tombait à 2 100 €, vous auriez perdu 30 %."
        + _figures(
            "3000 | cited | votre budget",
            "1500 | cited | moitié du budget",
            "2100 | cited | budget après la baisse",
            "30% | count | scénario de baisse illustratif",
        )
    )
    result = _ledger(tmp_path).validate_final_answer(answer)
    assert result.valid is True, result.issues


def test_a_cited_amount_whose_line_names_no_source_is_rejected(tmp_path: Path) -> None:
    result = _ledger(tmp_path).validate_final_answer(
        "Investissez 3 000 € maintenant." + _figures("3000 | cited | votre budget")
    )
    assert result.valid is False
    assert [issue["reason"] for issue in result.issues] == ["citation_not_visible"]


def test_a_budget_declared_count_is_still_rejected_and_told_the_way_out(tmp_path: Path) -> None:
    result = _ledger(tmp_path).validate_final_answer(
        "Avec votre budget de 3 000 €, commencez petit." + _figures("3000 | count | budget")
    )
    assert result.valid is False
    message = result.issues[0]["message"]
    assert "a count cannot carry a currency mark" in message
    assert "declare it cited" in message


def test_the_prompt_tells_the_model_how_to_declare_the_users_amounts() -> None:
    assert "An amount the user gave you" in _SYSTEM_PROMPT
    assert "is `cited` too, never `count`" in _SYSTEM_PROMPT
