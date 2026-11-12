"""An IPO order form read from a screenshot (2026-11-12, second rerun).

The answer quoted the user's order screen through ``analyze_image`` and
three of its figures were refused, which sent the gate after market data for
a stock not listed yet:

* the image's reading was never evidence, so "votre limite de 85 $" had no
  source at all;
* the reading wrote a key/value table, "| Limite ($) | **85** (rempli) |":
  the currency sits in the row's label and the word in the cell made the
  amount a count;
* "4 | count | nombre de trimestres pour annualiser" was not visible in
  "le 3e trimestre multiplié par 4", singular against plural.

A table cell also said "Je n'ai pas récupéré le taux EUR/USD" after an amount
and was refused for attaching that amount to EURUSD=X.

All values here are made up.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger

pytestmark = pytest.mark.unit

_READING = (
    "Écran d'ordre d'un courtier.\n\n"
    "| Champ | Valeur affichée |\n|---|---|\n"
    "| Type | **A cours limité** |\n"
    "| Limite ($) | **42** (rempli) |\n"
    "| Fourchette ($) | 30 – 60 |\n"
    "| Espace libre | **2 345,67 €** |\n"
)


def _ledger(tmp_path: Path) -> GroundingLedger:
    image = tmp_path / "uploads" / "shot.png"
    image.parent.mkdir()
    image.write_bytes(b"png")
    ledger = GroundingLedger(run_dir=tmp_path / "run", user_message="Je veux souscrire à l'IPO. Je mets quoi ?")
    ledger.ingest_tool_result(
        tool_name="analyze_image",
        arguments={"path": "uploads/shot.png"},
        result=json.dumps({"ok": True, "data": {"path": str(image), "question": "?", "answer": _READING}}),
        call_id="image-1",
        success=True,
    )
    return ledger


def _issues(ledger: GroundingLedger, sentence: str, *lines: str) -> list[dict]:
    answer = f"{sentence}\n\n```figures\n" + "\n".join(lines) + "\n```\n"
    return list(ledger.validate_final_answer(answer).issues)


def test_figures_read_from_a_screenshot_are_grounded(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Votre limite de 42 $ est dans la fourchette affichée de 30 à 60 $ ; votre espace libre est de 2 345,67 € (capture).",
        "42 | observed | limite saisie | analyze_image",
        "30 | observed | bas de la fourchette affichée | analyze_image",
        "60 | observed | haut de la fourchette affichée | analyze_image",
        "2 345,67 | observed | espace libre | analyze_image",
    )
    assert issues == []


def test_a_figure_the_screenshot_does_not_show_is_refused(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Votre limite de 47 $ (capture).",
        "47 | observed | limite saisie | analyze_image",
    )
    assert issues


def test_a_count_label_matches_its_singular(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    ledger.ingest_tool_result(
        tool_name="read_url",
        arguments={"url": "https://example.com/ipo"},
        result=json.dumps({"status": "ok", "url": "https://example.com/ipo", "content": "Q3 revenue $9.5B."}),
        call_id="read_url-1",
        success=True,
    )
    issues = _issues(
        ledger,
        "Le chiffre d'affaires du T3 est de 9.5 Md$ ; annualisé, environ 38 Md$ (le 3e trimestre multiplié par 4).",
        "9.5 | observed | CA T3 Md$ | read_url",
        "4 | count | nombre de trimestres pour annualiser",
        "38 | derived | 9.5 × 4 trimestres | read_url",
    )
    assert issues == []


def test_a_rate_reported_as_not_retrieved_does_not_take_the_amount_before_it(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "| Quantité | À vous de choisir | Votre espace libre est de 2 345,67 € (capture). "
        "Je n'ai pas récupéré le taux EUR/USD, donc je ne calcule pas de nombre d'actions. |",
        "2 345,67 | observed | espace libre | analyze_image",
    )
    assert [issue for issue in issues if issue.get("reason") == "symbol_never_handled"] == []


def test_a_rate_quoted_with_a_figure_is_still_refused(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Le taux EUR/USD est de 1.1234 aujourd'hui.",
        "1.1234 | observed | taux de change | analyze_image",
    )
    assert any(issue.get("reason") == "symbol_never_handled" for issue in issues)
