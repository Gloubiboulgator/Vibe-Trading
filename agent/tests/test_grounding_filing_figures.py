"""An IPO filing's figures quoted in an answer (2026-11-12).

"Je veux souscrire à l'IPO Anthropic" read the issuer's IPO website as filed
with the SEC. Its second draft was refused for two figures the page held:

* "(3) %" for a negative operating margin: a filing prints a negative in
  parentheses, "(3)% Operating Margin". The page gave no -3 and the
  declaration line could not be read at all.
* "68 | derived | 17,0 × 4 trimestres": the block also declared "4x |
  observed" (a compute-efficiency gain) above "4 | count", and the count was
  never found behind the first line holding 4.

The page here is shortened and its values are made up.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger
from src.agent.grounding.figures import parse_figures_block, scan_figures

pytestmark = pytest.mark.unit

_PAGE = (
    "Q3'26 Financial highlights $12.0B Revenue >9x YoY revenue >4x Compute efficiency gain "
    "since Q1'25 11% Adjusted Operating Margin (5)% Operating Margin As of September 30, 2026."
)
_REF = "read_url ipo-website"


def _ledger(tmp_path: Path) -> GroundingLedger:
    ledger = GroundingLedger(run_dir=tmp_path / "run", user_message="Je veux souscrire à l'IPO.")
    ledger.ingest_tool_result(
        tool_name="read_url",
        arguments={"url": "https://example.com/ipo-website"},
        result=json.dumps({"status": "ok", "url": "https://example.com/ipo-website", "content": _PAGE}),
        call_id="read_url-1",
        success=True,
    )
    return ledger


def _issues(ledger: GroundingLedger, sentence: str, *lines: str) -> list[dict]:
    answer = f"{sentence}\n\n```figures\n" + "\n".join(lines) + "\n```\n"
    return list(ledger.validate_final_answer(answer).issues)


def test_a_percent_in_parentheses_is_negative() -> None:
    text = "Margin (5)% and item (2) of the list"
    figures = [(f.value, f.percent) for f in scan_figures(text, parse_figures_block(text))]
    assert figures == [(-5.0, True), (2.0, False)]


@pytest.mark.parametrize("written", ["−5 %", "(5) %"])
def test_a_filing_s_negative_margin_is_grounded(tmp_path, written) -> None:
    issues = _issues(
        _ledger(tmp_path),
        f"La marge opérationnelle GAAP est de {written} au T3 (site IPO).",
        f"{written} | observed | marge opérationnelle GAAP | {_REF}",
    )
    assert issues == []


def test_a_count_declared_after_an_observation_of_the_same_value(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Revenu T3 de 12,0 Md$, gain d'efficacité de 4x ; annualisé : 12 Md$ × 4 trimestres = 48 Md$.",
        f"12,0 | observed | revenu T3 Md$ | {_REF}",
        f"4x | observed | gain d'efficacité | {_REF}",
        "4 | count | trimestres par an",
        f"48 | derived | 12,0 × 4 trimestres, run-rate Md$ | {_REF}",
    )
    assert [issue for issue in issues if issue.get("claim") == "48"] == []


def test_the_fallback_for_a_page_s_figures_does_not_ask_for_prices(tmp_path) -> None:
    # The run ended on "elle citait des prix que cette session n'a obtenus par
    # aucun outil" although no figure in either draft was a price.
    ledger = _ledger(tmp_path)
    ledger.validate_final_answer(
        "La marge ajustée est de 14 % (site IPO).\n\n```figures\n"
        f"14 % | observed | marge ajustée | {_REF}\n```\n"
    )
    message = ledger.safe_fallback()
    assert "prix" not in message and "sources" in message


def test_an_answer_on_an_unlisted_stock_is_released_cut(tmp_path) -> None:
    # The third rerun locked ANT.US, which has no price before its listing,
    # and its last draft failed on one cited figure: the whole answer was
    # replaced by the fallback instead of losing that figure.
    ledger = _ledger(tmp_path)
    ledger._identity_required = True
    draft = (
        "Le chiffre d'affaires du T3 est de 12.0 Md$ (site IPO).\n\n"
        "La dernière levée valorisait la société 640 Md$.\n\n```figures\n"
        f"12.0 | observed | CA T3 Md$ | {_REF}\n"
        "640 | cited | levée de mai, FinanceFeeds | web_search\n```\n"
    )
    validation = ledger.validate_final_answer(draft)
    assert [issue["reason"] for issue in validation.issues] == ["citation_not_visible"]

    released = ledger.redacted_release(draft, validation)

    assert released is not None
    assert "12.0" in released and "640" not in released
