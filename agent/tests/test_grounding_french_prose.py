"""A French answer reads its decimal commas even without a % or a glued € (2026-11-08 audit).

``_writes_decimal_commas`` switched a document to decimal commas only on local evidence
(a percent, a glued currency, "0,xx"). A French answer with none of them read "25,4" as
the bare integers 25 and 4, which are never checked: a wrong P/E, close or volume was
released, while the same mistake written "25.4" was rejected. A document written in
French now reads its single commas as decimals unless it also groups with commas.

The invariant pinned here is parity: each French sentence gets the verdict its English
twin gets.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger
from src.agent.grounding.figures import _numbers, _writes_decimal_commas

pytestmark = pytest.mark.unit

SRC_FR = " (source : yfinance)"
SRC_EN = " (source: yfinance)"


def _ledger(tmp_path: Path) -> GroundingLedger:
    ledger = GroundingLedger(run_dir=tmp_path, user_message="Analyse CW8.PA et MC.PA")
    ledger.ingest_tool_result(
        tool_name="get_market_data",
        arguments={"codes": ["CW8.PA", "MC.PA"]},
        result=json.dumps(
            {
                "CW8.PA": [{"trade_date": "2026-11-06T00:00:00", "open": 683.65, "high": 692.35,
                            "low": 682.91, "close": 692.3, "volume": 11736}],
                "MC.PA": [{"trade_date": "2026-11-06T00:00:00", "open": 405.0, "high": 410.0,
                           "low": 401.0, "close": 408.75, "volume": 1250000}],
            }
        ),
        call_id="prices",
        success=True,
    )
    return ledger


# (French, English twin); the value is right or wrong the same way in both.
_PAIRS = [
    # wrong values
    ("CW8.PA a clôturé à 702,30 euros, le cours est en baisse pour cette semaine" + SRC_FR + ".",
     "CW8.PA closed at 702.30 euros, the price is down for this week" + SRC_EN + "."),
    ("MC.PA a un PER de 25,4 fois les bénéfices selon les données de cette séance" + SRC_FR + ".",
     "MC.PA has a P/E of 25.4 times earnings according to this session's data" + SRC_EN + "."),
    ("MC.PA : le volume est de 2 250 000 titres pour cette séance, avec une baisse" + SRC_FR + ".",
     "MC.PA: the volume is 2,250,000 shares for this session, with a decline" + SRC_EN + "."),
    ("Pour MC.PA, le cours de clôture est de 418,75 dans cette séance" + SRC_FR + ".",
     "For MC.PA, the closing price is 418.75 in this session" + SRC_EN + "."),
    # right values
    ("CW8.PA a clôturé à 692,30 euros, le cours est en baisse pour cette semaine" + SRC_FR + ".",
     "CW8.PA closed at 692.30 euros, the price is down for this week" + SRC_EN + "."),
    ("Pour MC.PA, le cours de clôture est de 408,75 dans cette séance" + SRC_FR + ".",
     "For MC.PA, the closing price is 408.75 in this session" + SRC_EN + "."),
    ("MC.PA : le volume est de 1 250 000 titres pour cette séance, avec une baisse" + SRC_FR + ".",
     "MC.PA: the volume is 1,250,000 shares for this session, with a decline" + SRC_EN + "."),
]


@pytest.mark.parametrize(("french", "english"), _PAIRS)
def test_a_french_sentence_gets_the_verdict_of_its_english_twin(
    tmp_path: Path, french: str, english: str
) -> None:
    fr = _ledger(tmp_path / "fr").validate_final_answer(french)
    en = _ledger(tmp_path / "en").validate_final_answer(english)
    assert fr.valid is en.valid, (fr.issues, en.issues)


def test_wrong_french_figures_without_any_percent_are_rejected(tmp_path: Path) -> None:
    result = _ledger(tmp_path).validate_final_answer(
        "Pour MC.PA, le cours de clôture est de 418,75 dans cette séance" + SRC_FR + "."
    )
    assert result.valid is False
    assert "418,75" in [issue.get("claim") for issue in result.issues]


def test_french_prose_switches_the_document_to_decimal_commas() -> None:
    text = "Le PER de MC.PA est de 25,4 pour cette séance, avec une baisse des volumes."
    assert _writes_decimal_commas(text) is True
    assert [t.digits for t in _numbers(text)] == ["25.4"]


@pytest.mark.parametrize(
    "text",
    [
        # English prose: a lone "25,4" proves nothing, as before.
        "The P/E of MC.PA is 25,4 for this session, with lower volumes.",
        # French prose that groups with commas is a grouping document.
        "Le volume de MC.PA est de 1,250,000 titres pour cette séance, avec 25,4 points.",
        # Too little French to tell.
        "MC.PA 25,4",
    ],
)
def test_other_documents_keep_their_reading(text: str) -> None:
    assert _writes_decimal_commas(text) is False


def test_a_french_answer_that_writes_dot_decimals_keeps_them() -> None:
    """"6.177 €" in a French answer that also writes "1283.6" and "40.16" is 6.177:
    French prose switched the document to decimal commas and read it as 6177."""
    text = (
        "| ETF | Cours |\n|---|---|\n| DCAM.PA | 6.177 € |\n| PCEU.PA | 40.16 € |\n"
        "Une action ASML coûte 1283.6 €, ce qui pèse lourd dans ton budget pour cette séance."
    )
    assert _writes_decimal_commas(text) is False
    assert [t.digits for t in _numbers(text)] == ["6.177", "40.16", "1283.6"]
