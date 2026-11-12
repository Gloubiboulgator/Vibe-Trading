"""A valuation answer that computes from a prospectus page (2026-11-12).

"L'entreprise est-elle bien valorisée ?" read the share count and the price
range from a page, then derived the market value and a revenue growth rate.
Two drafts in a row were refused:

* one share count written "13,086,672,593" in the figures block made the
  whole French answer read as English, so "4,5 fois" became 45;
* "/ 1e9" to express billions was an operand nobody observed;
* "(234 / 81)^(1/4) − 1", a compound growth rate, was neither evaluated nor
  allowed its "− 1";
* "pour 1 $ de chiffre d'affaires" was an undeclared figure.

All values here are made up.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger

pytestmark = pytest.mark.unit

_PAGE = (
    "The company has 12,345,678,901 shares outstanding after the offering. "
    "The offering is priced between $60 and $64 per share. "
    "Revenue grew from $50 million in 2021 to $180 million in 2025."
)

_FRENCH = "Pour répondre, voici ce que dit la page et ce que j'en déduis pour vous, chiffre par chiffre. "


def _ledger(tmp_path: Path) -> GroundingLedger:
    ledger = GroundingLedger(run_dir=tmp_path / "run", user_message="L'entreprise est-elle bien valorisée ?")
    ledger.ingest_tool_result(
        tool_name="read_url",
        arguments={"url": "https://ipo.example.com/newco"},
        result=json.dumps({"status": "ok", "url": "https://ipo.example.com/newco", "content": _PAGE}),
        call_id="read_url-1",
        success=True,
    )
    return ledger


def _issues(ledger: GroundingLedger, prose: str, *lines: str) -> list[str]:
    answer = f"{_FRENCH}{prose}\n\n```figures\n" + "\n".join(lines) + "\n```\n"
    return [f"{issue.get('value')}:{issue['reason']}" for issue in ledger.validate_final_answer(answer).issues]


def test_a_market_value_in_billions_divides_by_a_unit(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "À 60 $ par action, les 12 345 678 901 actions valent 741 Md$, soit 4,1 fois les 180 M$ de revenu multipliés par mille.",
        "60 | observed | prix bas | read_url",
        "12345678901 | observed | actions | read_url",
        "741 | derived | 12,345,678,901 × 60 / 1e9 | read_url",
        "180 | observed | revenu 2025 | read_url",
        "4,1 | derived | 741 / 180 | read_url",
    )
    assert issues == []


def test_an_english_count_in_the_block_keeps_the_prose_french(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Le revenu a été multiplié par 3,6 entre 2021 et 2025.",
        "3,6 | derived | 180 / 50 | read_url",
        "12,345,678,901 | observed | actions | read_url",
    )
    assert issues == []


def test_a_compound_growth_rate_is_a_root_of_a_ratio_minus_one(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Le revenu a crû d'environ 38 % par an entre 2021 et 2025.",
        "38 % | derived | (180 / 50)^(1/4) − 1 | read_url",
    )
    assert issues == []


def test_a_wrong_compound_growth_rate_is_refused(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Le revenu a crû d'environ 45 % par an entre 2021 et 2025.",
        "45 % | derived | (180 / 50)^(1/4) − 1 | read_url",
    )
    assert issues and all(issue.endswith("derivation_result_mismatch") for issue in issues)


def test_a_one_after_per_is_a_unit_not_a_figure(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Le multiple dit combien vous payez pour 1 $ de revenu : ici 4,1 fois au prix bas.",
        "4,1 | derived | 12345678901 × 60 / 1e9 / 180 | read_url",
    )
    assert issues == []


def test_an_unobserved_operand_is_still_refused(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "À 70 $ par action, la société vaudrait 864 Md$.",
        "70 | proposed | prix hypothétique | hypothèse",
        "864 | derived | 12345678901 × 70 / 1e9 + 7 | read_url",
    )
    assert issues
