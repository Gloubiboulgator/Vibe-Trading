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


# The rerun after the fix, same day: TrendForce, ASML's buyback table and a
# Yahoo headline.


def test_an_english_dollar_range_in_billions_is_read_whole(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    page = (
        "While maintaining its 2026 capex guidance at US$60–64 billion, TSMC signaled plans. "
        "UBS expects spending to surge roughly 45% YoY to US$90 billion in 2027."
    )
    _read(ledger, {"status": "ok", "url": "https://example.com/tsmc", "content": page})
    issues = _issues(
        ledger,
        "TSMC maintient 60 à 64 Md USD d'investissements pour 2026 ; UBS attend 90 Md USD en 2027 (TrendForce).",
        "60 | observed | bas de fourchette, TrendForce | read_url",
        "64 | observed | haut de fourchette, TrendForce | read_url",
        "90 | observed | UBS 2027, TrendForce | read_url",
    )
    assert issues == []


def test_a_share_count_after_a_short_date_keeps_its_value(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    table = (
        "Date Shares Price Total\n"
        "04-Nov-26 73,500€1,356.80€99,724,484\n"
        "05-Nov-26 125,000€1,258.16€157,270,388\n"
    )
    ledger._session_symbols.add("ASML.AS")
    _read(ledger, {"status": "ok", "url": "https://example.com/buyback", "content": table})
    issues = _issues(
        ledger,
        "Le 05/11/2026, ASML.AS a racheté 125000 titres à 1258.16 EUR en moyenne (communiqué).",
        "125000 | observed | titres rachetés le 05/11/2026 | read_url",
        "1258.16 | observed | prix moyen le 05/11/2026 | read_url",
    )
    assert issues == []


def test_a_news_headline_grounds_its_figure(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    _read(
        ledger,
        {"ok": True, "status": "ok", "data": {"code": "ASML.US", "articles": [
            {"title": "ASML Stock May Be Priced For Perfection After 125% Run",
             "url": "https://example.com/n", "snippet": ""},
        ]}},
        tool="get_stock_news",
        arguments={"code": "ASML.US"},
    )
    issues = _issues(
        ledger,
        "Simply Wall St titre qu'ASML pourrait être valorisé pour la perfection après une hausse de 125 %.",
        "125 % | observed | titre Simply Wall St | get_stock_news",
    )
    assert issues == []


def test_a_short_date_s_year_is_not_glued_to_the_next_number() -> None:
    from src.agent.grounding.figures import parse_figures_block, scan_figures

    row = "05-Nov-26 125,000€1,258.16€157,270,388"
    values = [figure.value for figure in scan_figures(row, parse_figures_block(row)) if figure.shape == "measured"]
    assert values == [125000, 1258.16, 157270388]


# The third rerun: an analyst-target page and a share of sales applied to the
# company's guidance.


def test_a_page_s_bare_dollar_is_the_us_dollar(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    page = "Current Price$1507.85\n\nAverage Target$2330.75\n\nLow$2100.00\n\nHigh$2623.00"
    _read(ledger, {"status": "ok", "url": "https://example.com/targets", "content": page})
    issues = _issues(
        ledger,
        "Selon vcpscanner, l'objectif moyen est de 2330.75 USD, dans une fourchette de 2100 à 2623 USD.",
        "2330.75 | observed | objectif moyen, vcpscanner | read_url",
        "2100 | observed | objectif bas, vcpscanner | read_url",
        "2623 | observed | objectif haut, vcpscanner | read_url",
    )
    assert issues == []


def test_a_prefixed_dollar_is_not_the_us_dollar(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    _read(ledger, {"status": "ok", "url": "https://example.com/hk", "content": "Target HK$2330.75"})
    issues = _issues(
        ledger,
        "L'objectif est de 2330.75 USD (page lue).",
        "2330.75 | observed | objectif | read_url",
    )
    assert issues


def test_a_formula_written_in_the_prose_s_unit_is_checked_in_it(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    _read(ledger, {"status": "ok", "url": "https://example.com/guidance",
                   "content": "ASML expects 2026 total net sales between €44 billion and €45 billion. "
                              "China should be about 20% of 2026 sales."})
    issues = _issues(
        ledger,
        "Appliqué à la prévision d'ASML, cela donne 8.8 à 9.0 milliards d'euros.",
        "8.8 | derived | 44 × 20 % | read_url",
        "9.0 | derived | 45 × 20 % | read_url",
    )
    assert issues == []
    wrong = _issues(
        ledger,
        "Appliqué à la prévision d'ASML, cela donne 9.6 milliards d'euros.",
        "9.6 | derived | 44 × 20 % | read_url",
    )
    assert [issue["reason"] for issue in wrong] == ["derivation_result_mismatch"]


# The fourth rerun: Dutch snippets and a Belgian page.


def _search(ledger: GroundingLedger, *items: tuple[str, str]) -> None:
    _read(
        ledger,
        {"status": "ok", "query": "ASML", "results": [
            {"title": title, "url": "https://example.com", "snippet": snippet} for title, snippet in items
        ]},
        tool="web_search",
        arguments={"query": "ASML"},
    )


def test_each_snippet_keeps_its_own_number_notation(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    _search(
        ledger,
        ("Aandeel ASML Holding", "Laatste koers (eur) 1.403,800 11 nov 2026 Verschil +42,800 +3,14%"),
        ("ASML sales", "ASML shipped 1,234 systems for $28,262 million."),
    )
    issues = _issues(
        ledger,
        "Le titre a gagné 42.80 EUR sur la séance (belegger.nl).",
        "42.80 | observed | variation du 11/11, belegger.nl | web_search",
    )
    assert issues == []


def test_a_unit_written_as_a_word_marks_a_page_figure(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    _search(
        ledger,
        ("ASML Technische Analyse", "Het aandeel test de weerstand bij 1370 euro."),
        ("TSMC ziet omzet in oktober met bijna 60 procent stijgen", ""),
    )
    issues = _issues(
        ledger,
        "Investtech situe une résistance à 1370 EUR ; le chiffre d'affaires d'octobre de TSMC a progressé de près de 60 %.",
        "1370 | observed | résistance, Investtech | web_search",
        "60 % | observed | hausse d'octobre de TSMC, Business AM | web_search",
    )
    assert issues == []


def test_a_page_in_another_currency_still_contradicts(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    _search(ledger, ("ASML", "Het aandeel test de weerstand bij 1370 dollar."))
    issues = _issues(
        ledger,
        "Investtech situe une résistance à 1370 EUR.",
        "1370 | observed | résistance, Investtech | web_search",
    )
    assert issues
