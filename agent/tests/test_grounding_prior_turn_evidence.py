"""Follow-up questions answer from what earlier turns fetched (2026-11-12).

"Compare à l'IPO SpaceX", then "Et Uber ?": each follow-up reused the closes
and pages the earlier turns of the session had read. The gate only knew the
current run's calls, so every return over those closes was refused as an
unobserved operand and ten figures were cut from one answer.

All values here are made up.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger
from src.agent.grounding.ledger import load_prior_evidence

pytestmark = pytest.mark.unit

_FRENCH = "Pour répondre, voici ce que disent les données et ce que j'en déduis pour vous, chiffre par chiffre. "


def _first_turn(tmp_path: Path) -> Path:
    run_dir = tmp_path / "turn1"
    ledger = GroundingLedger(run_dir=run_dir, user_message="Compare à une autre introduction en bourse.")
    ledger.ingest_tool_result(
        tool_name="read_url",
        arguments={"url": "https://ipo.example.com/otherco"},
        result=json.dumps({"status": "ok", "url": "https://ipo.example.com/otherco", "content": (
            "Otherco priced its offering at $120 per share. The stock closed last week at $131.475."
        )}),
        call_id="read_url-turn1",
        success=True,
    )
    ledger.persist()
    return run_dir


def _second_turn(tmp_path: Path, runs: list[Path]) -> GroundingLedger:
    return GroundingLedger(
        run_dir=tmp_path / "turn2",
        user_message="Et depuis l'introduction ?",
        prior_evidence=load_prior_evidence(runs),
    )


def _issues(ledger: GroundingLedger, prose: str, *lines: str) -> list[str]:
    answer = f"{_FRENCH}{prose}\n\n```figures\n" + "\n".join(lines) + "\n```\n"
    return [f"{issue.get('value')}:{issue['reason']}" for issue in ledger.validate_final_answer(answer).issues]


def test_a_return_over_an_earlier_turn_s_observations_is_grounded(tmp_path) -> None:
    ledger = _second_turn(tmp_path, [_first_turn(tmp_path)])
    issues = _issues(
        ledger,
        "Introduite à 120 USD, l'action a clôturé à 131,475 USD, soit +9,6 %.",
        "120 | observed | prix d'introduction, USD | read_url",
        "131,475 | observed | dernière clôture, USD | read_url",
        "+9,6 % | derived | 131,475 / 120 − 1 | read_url",
    )
    assert issues == []


def test_a_ref_to_the_prior_turn_names_its_observations(tmp_path) -> None:
    ledger = _second_turn(tmp_path, [_first_turn(tmp_path)])
    issues = _issues(
        ledger,
        "Introduite à 120 USD, l'action a gagné 9,6 % depuis.",
        "120 | observed | prix d'introduction, USD | tour précédent",
        "+9,6 % | derived | 131,475 / 120 − 1 | prior turn",
    )
    assert issues == []


def test_without_the_earlier_turn_the_return_is_still_refused(tmp_path) -> None:
    ledger = _second_turn(tmp_path, [])
    issues = _issues(
        ledger,
        "Introduite à 120 USD, l'action a gagné 9,6 % depuis.",
        "+9,6 % | derived | 131,475 / 120 − 1 | read_url",
    )
    assert issues


def test_a_value_no_turn_observed_is_still_refused(tmp_path) -> None:
    ledger = _second_turn(tmp_path, [_first_turn(tmp_path)])
    issues = _issues(
        ledger,
        "Introduite à 100 USD, l'action a gagné 31,5 % depuis.",
        "+31,5 % | derived | 131,475 / 100 − 1 | read_url",
    )
    assert issues


def test_carried_observations_are_not_persisted_again(tmp_path) -> None:
    ledger = _second_turn(tmp_path, [_first_turn(tmp_path)])
    ledger.persist()
    stored = json.loads(next((tmp_path / "turn2").rglob("*.json")).read_text(encoding="utf-8"))
    assert stored["evidence"] == []
    assert load_prior_evidence([tmp_path / "turn2"]) == []
