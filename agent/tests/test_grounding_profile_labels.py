"""A ratio declared by its label and symbol is checked against that profile field (2026-11-09).

A PEA screen declared "12.0 | observed | PER prévisionnel | RI.PA": the note
names the ratio, the ref the instrument, and get_stock_profile had returned
forwardPE 12.004. The unscoped pool held only market data, so 30 cells of the
table read "(omis※)".
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger

pytestmark = pytest.mark.unit

PROFILE = {
    "ok": True,
    "market": "us",
    "source": "yahoo",
    "data": {
        "ticker": "RI.PA",
        "listing": {"symbol": "RI.PA", "exchange": "PAR", "currency": "EUR", "financial_currency": "EUR"},
        "sections": {"key_stats": {
            "forwardPE": 12.004401, "trailingPE": 15.2, "priceToBook": 1.1551327, "revenueGrowth": -0.132,
            "operatingMargins": 0.196, "targetMeanPrice": 80.66, "beta": 0.52,
        }},
    },
}


def _issues(line: str, block: str) -> list[str]:
    ledger = GroundingLedger(run_dir=Path(tempfile.mkdtemp()), user_message="Analyse Pernod Ricard pour mon PEA")
    ledger.ingest_tool_result(
        tool_name="get_stock_profile", arguments={"ticker": "RI.PA"},
        result=json.dumps(PROFILE), call_id="p1", success=True,
    )
    # A French answer: its percents written with a decimal comma tell the
    # scanner that "12,0" is one number, not the list "12, 0".
    prose = f"La marge opérationnelle de RI.PA atteint 19,6 %. {line}"
    block = f"19.6% | observed | marge opérationnelle | RI.PA\n{block}"
    result = ledger.validate_final_answer(f"{prose}\n\n```figures\n{block}\n```")
    return [issue.get("claim") for issue in result.issues]


@pytest.mark.parametrize(
    ("line", "block"),
    [
        ("Le PER prévisionnel de RI.PA est de 12,0.", "12.0 | observed | PER prévisionnel | RI.PA"),
        ("Prix / valeur comptable de RI.PA : 1,16.", "1.16 | observed | prix/valeur comptable | RI.PA"),
        ("Le chiffre d'affaires de RI.PA recule de 13,2 %.", "-13.2% | observed | croissance du CA | RI.PA"),
        ("Objectif moyen des analystes pour RI.PA : 80,66.", "80.66 | observed | objectif moyen | RI.PA"),
        ("Bêta de RI.PA : 0,52.", "0.52 | observed | bêta | RI.PA"),
    ],
)
def test_a_labelled_profile_ratio_is_grounded(line: str, block: str) -> None:
    assert _issues(line, block) == []


def test_a_wrong_value_is_still_refused() -> None:
    assert _issues("Prix / valeur comptable de RI.PA : 1,45.", "1.45 | observed | prix/valeur comptable | RI.PA") == ["1,45"]
    assert _issues("Le PER prévisionnel de RI.PA est de 13,5.", "13.5 | observed | PER prévisionnel | RI.PA") == ["13,5"]
    assert _issues("Bêta de RI.PA : 0,9.", "0.9 | observed | bêta | RI.PA") == ["0,9"]


def test_no_label_no_match() -> None:
    assert _issues("Un chiffre de RI.PA : 1,16.", "1.16 | observed | indicateur | RI.PA") == ["1,16"]
