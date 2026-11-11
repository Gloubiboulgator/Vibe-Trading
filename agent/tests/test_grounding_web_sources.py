"""Figures quoted from a web page or a search snippet (2026-11-11).

"Approfondis la recherche d'actualité" on ASML read eight articles and quoted
their figures ("chiffre d'affaires du T3 11.66 Md EUR", "marge brute 57.5 %",
"20 % des ventes selon 24/7 Wall St"), each declared "observed | read_url".
The pages held them, but a page is prose and only numeric JSON leaves became
evidence: every draft was refused "not in the referenced call" and the gate
asked for market data again, four times, before the model dropped the news.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger

pytestmark = pytest.mark.unit

_PAGE = (
    "Title: ASML Q3 2026 results\n\n"
    "| Metric | Q3 2026 | Q2 2026 |\n| --- | --- | --- |\n"
    "| Total net sales | €11.66 billion | €9.33 billion |\n"
    "| Gross margin | 57.5% | 54.0% |\n\n"
    "ASML expects fourth-quarter sales of €14.2 billion to €15.2 billion. "
    "ASML says it already plans 30% more capacity in 2027 than in 2026."
)


def _ledger(tmp_path: Path) -> GroundingLedger:
    return GroundingLedger(run_dir=tmp_path / "run", user_message="Approfondis la recherche d'actualité")


def _read(ledger: GroundingLedger, payload: dict, tool: str = "read_url", arguments: dict | None = None) -> None:
    ledger.ingest_tool_result(
        tool_name=tool,
        arguments=arguments or {"url": "https://example.com/asml-q3"},
        result=json.dumps(payload),
        call_id=f"{tool}-1",
        success=payload.get("status") == "ok",
    )


def _issues(ledger: GroundingLedger, sentence: str, *lines: str) -> list[dict]:
    answer = f"{sentence}\n\n```figures\n" + "\n".join(lines) + "\n```\n"
    return list(ledger.validate_final_answer(answer).issues)


def test_figures_from_a_read_page_are_grounded(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    _read(ledger, {"status": "ok", "url": "https://example.com/asml-q3", "content": _PAGE})
    issues = _issues(
        ledger,
        "Au T3, ASML a réalisé 11.66 Md EUR de ventes avec une marge brute de 57.5 %, "
        "et vise 14.2 à 15.2 Md EUR au T4 (techaiwire).",
        "11.66 | observed | ventes T3, techaiwire | read_url",
        "57.5 % | observed | marge brute T3, techaiwire | read_url",
        "14.2 | observed | bas de la prévision T4, techaiwire | read_url",
        "15.2 | observed | haut de la prévision T4, techaiwire | read_url",
    )
    assert issues == []


def test_a_figure_the_page_does_not_hold_is_still_refused(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    _read(ledger, {"status": "ok", "url": "https://example.com/asml-q3", "content": _PAGE})
    issues = _issues(
        ledger,
        "La marge brute du T3 est de 61.2 % (techaiwire).",
        "61.2 % | observed | marge brute T3, techaiwire | read_url",
    )
    assert issues


def test_a_failed_read_grounds_nothing(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    _read(ledger, {"status": "error", "error": f"remote reader returned HTTP 422: {_PAGE}"})
    issues = _issues(
        ledger,
        "La marge brute du T3 est de 57.5 % (techaiwire).",
        "57.5 % | observed | marge brute T3, techaiwire | read_url",
    )
    assert issues


def test_a_search_snippet_grounds_its_figure(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    _read(
        ledger,
        {
            "status": "ok",
            "query": "ASML China sales 2026",
            "results": [
                {"title": "ASML and China", "url": "https://example.com/a",
                 "snippet": "China would account for about 20% of ASML sales in 2026."},
                {"title": "ASML falls 8% after the election", "url": "https://example.com/b", "snippet": ""},
            ],
        },
        tool="web_search",
        arguments={"query": "ASML China sales 2026"},
    )
    issues = _issues(
        ledger,
        "La Chine pèserait environ 20 % des ventes 2026, et le titre a perdu 8 % après l'élection.",
        "20 % | observed | part de la Chine, 24/7 Wall St | web_search",
        "8 % | observed | baisse après l'élection | web_search",
    )
    assert issues == []
