"""A valuation answer over a news article and a search snippet (2026-11-12).

"L'entreprise est-elle bien valorisée ?" on an IPO read TechCrunch and a
Zacks snippet, then declared its ratios "17,3x | derived | 1404 / 81 |
techcrunch". Four drafts in a row were refused and the fifth passed only by
dropping every valuation multiple:

* the ref named the site, not the tool, and nothing read "techcrunch" as
  the page fetched from techcrunch.com; a snippet kept no url at all;
* "1404" in billions never met the page's "$1.404 trillion";
* each refusal looked like a missing price, so the gate fetched market data
  for a stock not listed yet, three times, after the first "no data".

All values here are made up.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger
from src.agent.grounding.identity import IdentityRecord

pytestmark = pytest.mark.unit

_ARTICLE = (
    "The range would value the company at $1.212 trillion on a fully diluted basis. "
    "Run-rate revenue reached $60 billion by the end of October."
)


def _ledger(tmp_path: Path) -> GroundingLedger:
    ledger = GroundingLedger(run_dir=tmp_path / "run", user_message="L'entreprise est-elle bien valorisée ?")
    ledger.ingest_tool_result(
        tool_name="read_url",
        arguments={"url": "https://news.example-wire.com/ipo"},
        result=json.dumps({"status": "ok", "url": "https://techcrunch.com/2026/11/10/ipo-range", "content": _ARTICLE}),
        call_id="read_url-1",
        success=True,
    )
    ledger.ingest_tool_result(
        tool_name="web_search",
        arguments={"query": "ipo valuation"},
        result=json.dumps({"status": "ok", "results": [
            {"title": "IPO guide", "url": "https://www.zacks.com/ipo-guide",
             "snippet": "The price range would value the company between $1.1 trillion and $1.212 trillion."},
        ]}),
        call_id="web_search-1",
        success=True,
    )
    return ledger


# A real answer is long enough for its French to set the decimal comma.
_FRENCH = "Pour répondre, voici ce que disent les sources et ce que j'en déduis pour vous. "


def _issues(ledger: GroundingLedger, sentence: str, *lines: str) -> list[dict]:
    answer = f"{_FRENCH}{sentence}\n\n```figures\n" + "\n".join(lines) + "\n```\n"
    return list(ledger.validate_final_answer(answer).issues)


def test_a_ratio_over_a_site_s_figures_is_anchored_by_the_site_s_name(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Selon TechCrunch, 1 212 Md$ de valorisation pour 60 Md$ de revenu annualisé, soit 20,2 fois.",
        "1212 | cited | valorisation, TechCrunch | techcrunch",
        "60 | cited | revenu annualisé, TechCrunch | techcrunch",
        "20,2 | derived | 1212 / 60 | techcrunch",
    )
    assert issues == []


def test_a_snippet_is_named_by_its_site(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Selon Zacks, la valorisation irait de 1 100 Md$ ; rapportée aux 60 Md$ de revenu de TechCrunch, 18,3 fois.",
        "1100 | cited | valorisation basse, Zacks | zacks",
        "60 | cited | revenu annualisé, TechCrunch | techcrunch",
        "18,3 | derived | 1100 / 60 | zacks, techcrunch",
    )
    assert issues == []


def test_a_site_that_was_not_read_anchors_nothing(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Selon Reuters, 20,2 fois le revenu.",
        "20,2 | derived | 1212 / 60 | reuters",
    )
    assert issues


def test_a_wrong_ratio_over_a_site_is_still_refused(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Selon TechCrunch, 1 212 Md$ de valorisation pour 60 Md$ de revenu, soit 25,0 fois.",
        "1212 | cited | valorisation, TechCrunch | techcrunch",
        "60 | cited | revenu annualisé, TechCrunch | techcrunch",
        "25,0 | derived | 1212 / 60 | techcrunch",
    )
    assert [issue["reason"] for issue in issues] == ["derivation_result_mismatch"]


def _locked(ledger: GroundingLedger, symbol: str) -> None:
    ledger._identities["ipo"] = IdentityRecord(query="ipo", status="locked", symbol=symbol, venue="us")


def test_no_market_data_for_the_locked_symbol_stops_price_recovery(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    _locked(ledger, "NEWCO.US")
    draft = "NEWCO.US cote 50.00 USD.\n\n```figures\n50.00 | observed | cours | get_market_data\n```\n"
    validation = ledger.validate_final_answer(draft)
    assert ledger.recovery_action(validation) == "get_market_data"

    ledger.ingest_tool_result(
        tool_name="get_market_data",
        arguments={"codes": ["NEWCO.US"]},
        result=json.dumps({"status": "error", "error_code": "no_market_data",
                           "error": "No data returned for any requested symbol: NEWCO.US"}),
        call_id="md-1",
        success=False,
    )
    assert ledger.recovery_action(ledger.validate_final_answer(draft)) is None


def test_a_derived_figure_without_anchor_is_not_a_missing_price(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    _locked(ledger, "NEWCO.US")
    validation = ledger.validate_final_answer(
        "Le multiple est de 20,2 (calcul).\n\n```figures\n20,2 | derived | 1212 / 60 | reuters\n```\n"
    )
    assert validation.issues
    assert ledger.recovery_action(validation) is None


def test_a_ref_naming_nothing_is_said_to_name_nothing(tmp_path) -> None:
    issues = _issues(
        _ledger(tmp_path),
        "Selon Reuters, 20,2 fois le revenu.",
        "20,2 | derived | 1212 / 60 | reuters",
    )
    assert any("'reuters', which names no evidence" in issue["message"] for issue in issues)
