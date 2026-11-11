"""Figures an ASML answer wrote correctly and the gate refused (2026-11-11).

The rerun of "C'est le bon moment pour acheter ASML ?" went through four
drafts, each refused for the same figures, before an answer with raw values:

* "12.7 Md EUR" of cash was compared with 12.7, not 12 735 099 904: the French
  scale word was not read.
* "le MACD est négatif (−45.0)" declared as "45.0 | observed | macd_line
  (−44.979)" was undeclared: a signed figure did not find its unsigned line.
* "+16.0 %" with ref "ASML.AS get_market_data" had no anchors: only the
  "get_market_data ASML.AS" order was read.
* "volume 2026-11-05 1602606 / volume.sma_20 727996.65" was not arithmetic:
  the date and the field name's digits stayed in the formula.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger
from src.agent.grounding.evidence import EvidenceRecord
from src.agent.grounding.figures import magnitude_suffix
from src.agent.grounding.policies import _formula_in_note

pytestmark = pytest.mark.unit


def _record(tool: str, field: str, value: float, day: str = "2026-11-11") -> EvidenceRecord:
    return EvidenceRecord(
        call_id=f"{tool}-1",
        tool=tool,
        symbol="ASML.AS",
        source="yahoo",
        timestamp=f"{day}T00:00:00",
        field=field,
        value=value,
        status="observed",
        currency="EUR",
        venue="euronext_amsterdam",
        currency_conversion="none",
    )


def _ledger(tmp_path: Path) -> GroundingLedger:
    ledger = GroundingLedger(run_dir=tmp_path, user_message="C'est le bon moment pour acheter ASML ?")
    ledger._evidence = [
        _record("get_market_data", "close", 1403.8),
        _record("get_market_data", "low", 1210.6, "2026-11-05"),
        _record("get_market_data", "high", 1431.6, "2026-11-02"),
        _record("get_market_data", "volume", 1602606.0, "2026-11-05"),
        _record("get_stock_profile", "data.sections.financials.totalCash", 12735099904),
        _record("technical_indicators", "indicators.macd.macd_line", -44.979),
        _record("technical_indicators", "indicators.volume.sma_20", 727996.65),
    ]
    ledger._session_symbols.add("ASML.AS")
    return ledger


def _answer(sentence: str, line: str) -> str:
    return (
        f"ASML.AS (Yahoo) cote 1403.80 EUR.\n\n{sentence}\n\n"
        "```figures\n"
        "1403.80 | observed | close | get_market_data\n"
        f"{line}\n"
        "```\n"
    )


def _issues(tmp_path: Path, sentence: str, line: str) -> list[dict]:
    return list(_ledger(tmp_path).validate_final_answer(_answer(sentence, line)).issues)


@pytest.mark.parametrize("word", ["Md", "Mds", "milliards", "Mrd"])
def test_a_french_scale_word_scales_the_figure(tmp_path, word) -> None:
    issues = _issues(
        tmp_path,
        f"La trésorerie est de 12.7 {word} EUR.",
        "12.7 | observed | totalCash | get_stock_profile",
    )
    assert issues == []


def test_scale_words_read_as_their_magnitude() -> None:
    assert magnitude_suffix("12,7 Md€", 4)[0] == 1e9
    assert magnitude_suffix("3 millions d'euros", 1)[0] == 1e6
    # A word that only starts like one is not a scale.
    assert magnitude_suffix("3 Mdx", 1)[0] == 1.0
    assert magnitude_suffix("3 milliardaires", 1)[0] == 1.0


def test_a_wrong_scaled_amount_is_still_refused(tmp_path) -> None:
    issues = _issues(
        tmp_path,
        "La trésorerie est de 12.7 millions EUR.",
        "12.7 | observed | totalCash | get_stock_profile",
    )
    assert issues


def test_a_signed_figure_finds_its_unsigned_declaration(tmp_path) -> None:
    issues = _issues(
        tmp_path,
        "Le MACD est négatif (−45.0).",
        "45.0 | observed | macd_line (−44.979) | technical_indicators",
    )
    assert issues == []


def test_a_signed_figure_still_meets_the_formula_s_sign(tmp_path) -> None:
    # Declared as the size of the fall, written as a fall: found, then refused
    # with the hint that the formula runs the other way, not as undeclared.
    [issue] = _issues(
        tmp_path,
        "Du plus haut au plus bas, soit −15.4 %.",
        "15.4 % | derived | (1431.60 − 1210.60) / 1431.60 | get_market_data",
    )
    assert issue["reason"] == "derivation_result_mismatch"
    assert issue["sign_reversed"] is True


def test_a_symbol_then_tool_ref_anchors_a_derivation(tmp_path) -> None:
    issues = _issues(
        tmp_path,
        "Le rebond atteint +16.0 % depuis le creux.",
        "16.0 % | derived | (1403.80 − 1210.60) / 1210.60 | ASML.AS get_market_data",
    )
    assert issues == []


def test_dates_and_field_names_leave_the_formula_readable(tmp_path) -> None:
    note = "volume 2026-11-05 1602606 / volume.sma_20 727996.65"
    result, operands, _ = _formula_in_note(note)
    assert operands == [1602606, 727996.65]
    assert result == pytest.approx(2.2014, rel=1e-4)
    issues = _issues(
        tmp_path,
        "Le volume du 05/11 vaut 2.2 fois la moyenne sur 20 séances.",
        f"2.2 | derived | {note} | get_market_data, technical_indicators",
    )
    assert issues == []
