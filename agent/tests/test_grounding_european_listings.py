"""European listings (CW8.PA, SAP.DE, NESN.SW) are known to the grounding identity layer.

The identity layer listed no European venue, so ``_infer_currency("CW8.PA")`` was None
and the evidence for a Paris ETF carried no currency. A close written "692,30 €" is a
EUR-marked figure and is compared only against EUR evidence, so an exact close was cut
to "(omitted※)": every price of a live PEA ETF table was lost this way (2026-11-08).

The suffixes are matched in uppercase only: ``.de``, ``.co``, ``.br``, ``.pa`` are also
web domains, and a source URL must not read as a ticker (as ``us.reuters`` once did).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger
from src.agent.grounding.identity import _infer_currency, _infer_venue, _scan_symbols

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("symbol", "currency"),
    [
        ("CW8.PA", "EUR"),
        ("MC.PA", "EUR"),
        ("SAP.DE", "EUR"),
        ("ASML.AS", "EUR"),
        ("ABI.BR", "EUR"),
        ("ENI.MI", "EUR"),
        ("SAN.MC", "EUR"),
        ("EDP.LS", "EUR"),
        ("RYA.IR", "EUR"),
        ("NOKIA.HE", "EUR"),
        ("OMV.VI", "EUR"),
        ("NESN.SW", "CHF"),
        ("VOLV-B.ST", "SEK"),
        ("NOVO-B.CO", "DKK"),
        ("EQNR.OL", "NOK"),
    ],
)
def test_european_listings_have_a_venue_and_a_currency(symbol: str, currency: str) -> None:
    assert _scan_symbols(f"{symbol} a clôturé hier.") == {symbol}
    assert _infer_venue(symbol) is not None
    assert _infer_currency(symbol) == currency


@pytest.mark.parametrize(
    "text",
    [
        "Source : https://www.boerse-frankfurt.de/etf",
        "voir site.co et exemple.br",
        "Données sur boursorama.pa ou finanzen.de",
    ],
)
def test_lowercase_web_domains_are_not_read_as_tickers(text: str) -> None:
    assert _scan_symbols(text) == set()


def _ledger(tmp_path: Path, symbol: str, close: float) -> GroundingLedger:
    ledger = GroundingLedger(run_dir=tmp_path, user_message="cours")
    ledger.ingest_tool_result(
        tool_name="get_market_data",
        arguments={"codes": [symbol]},
        result=json.dumps(
            {
                symbol: [
                    {
                        "trade_date": "2026-11-06T00:00:00",
                        "open": close * 0.99,
                        "high": close * 1.001,
                        "low": close * 0.98,
                        "close": close,
                        "volume": 11736,
                    }
                ]
            }
        ),
        call_id="prices",
        success=True,
    )
    return ledger


@pytest.mark.parametrize(
    ("symbol", "close", "prose"),
    [
        ("CW8.PA", 692.3, "CW8.PA a clôturé à 692,30 € le 06/11/2026."),
        ("CW8.PA", 692.3, "| ETF | Prix au 06/11/2026 |\n|---|---|\n| CW8.PA (MSCI World) | 692,30 € |"),
        ("SAP.DE", 210.75, "SAP.DE closed at 210.75 EUR."),
        ("NESN.SW", 81.4, "NESN.SW closed at CHF 81.40."),
        ("VOLV-B.ST", 250.4, "VOLV-B.ST closed at 250.40 SEK."),
    ],
)
def test_an_exact_european_close_in_its_currency_survives(
    tmp_path: Path, symbol: str, close: float, prose: str
) -> None:
    result = _ledger(tmp_path, symbol, close).validate_final_answer(prose)
    assert result.valid is True, result.issues


def test_a_wrong_european_close_is_still_rejected(tmp_path: Path) -> None:
    result = _ledger(tmp_path, "CW8.PA", 692.3).validate_final_answer(
        "CW8.PA a clôturé à 712,30 € le 06/11/2026."
    )
    assert result.valid is False
    assert "712,30" in [issue.get("claim") for issue in result.issues]


def test_a_european_close_in_the_wrong_currency_is_rejected(tmp_path: Path) -> None:
    result = _ledger(tmp_path, "CW8.PA", 692.3).validate_final_answer(
        "CW8.PA a clôturé à 692,30 USD."
    )
    assert result.valid is False


# --- day-first dates ---------------------------------------------------------------------
# "716,25 € (13/10/2026)" in a table cell: a day above 12 did not read as a date, so
# "13" and "10" were measured integers and cut, while "(09/10/2026)" passed as MM/DD.


@pytest.mark.parametrize("date", ["13/10/2026", "09/10/2026", "31.12.2025", "13-10-2026", "6/11/2026"])
def test_a_day_first_date_in_a_table_cell_is_structure(tmp_path: Path, date: str) -> None:
    result = _ledger(tmp_path, "CW8.PA", 692.3).validate_final_answer(
        "| ETF | Cours (source yfinance) |\n|---|---|\n"
        f"| CW8.PA | 692,30 € ({date}) |"
    )
    assert result.valid is True, result.issues


def test_a_measured_figure_beside_a_day_first_date_is_still_checked(tmp_path: Path) -> None:
    result = _ledger(tmp_path, "CW8.PA", 692.3).validate_final_answer(
        "| ETF | Cours (source yfinance) |\n|---|---|\n| CW8.PA | 702,30 € (13/10/2026) |"
    )
    assert result.valid is False
    assert [issue.get("claim") for issue in result.issues if issue.get("claim")] == ["702,30"]


# --- French numbers and tickers inside a derived note ------------------------------------
# "−3,3 % | derived | (692,30 − 716,25) / 716,25 pour CW8.PA": the comma was stripped as
# grouping (operands 69230 and 71625, never observed) and the ticker's "8." broke the parse,
# so every drawdown of the live table was cut.


def _two_bar_ledger(tmp_path: Path) -> GroundingLedger:
    ledger = GroundingLedger(run_dir=tmp_path, user_message="cours")
    ledger.ingest_tool_result(
        tool_name="get_market_data",
        arguments={"codes": ["CW8.PA"]},
        result=json.dumps(
            {
                "CW8.PA": [
                    {"trade_date": "2026-10-13T00:00:00", "open": 717.95, "high": 719.95,
                     "low": 716.15, "close": 716.25, "volume": 5966},
                    {"trade_date": "2026-11-06T00:00:00", "open": 683.65, "high": 692.35,
                     "low": 682.91, "close": 692.3, "volume": 11736},
                ]
            }
        ),
        call_id="prices",
        success=True,
    )
    return ledger


@pytest.mark.parametrize(
    "note",
    [
        "(692,30 − 716,25) / 716,25 pour CW8.PA",
        "(692,30 − 716,25) / 716,25",
        "(692.30 − 716.25) / 716.25 for CW8.PA",
    ],
)
def test_a_drawdown_derived_in_french_notation_is_verified(tmp_path: Path, note: str) -> None:
    result = _two_bar_ledger(tmp_path).validate_final_answer(
        "CW8.PA (yfinance, EUR) : −3,3 % depuis le plus haut."
        f"\n\n```figures\n−3,3 % | derived | {note} | get_market_data\n```"
    )
    assert result.valid is True, result.issues


def test_a_wrong_drawdown_in_french_notation_is_still_rejected(tmp_path: Path) -> None:
    result = _two_bar_ledger(tmp_path).validate_final_answer(
        "CW8.PA (yfinance, EUR) : −5,3 % depuis le plus haut."
        "\n\n```figures\n−5,3 % | derived | (692,30 − 716,25) / 716,25 pour CW8.PA | get_market_data\n```"
    )
    assert result.valid is False


def test_an_unobserved_operand_in_a_french_note_is_still_rejected(tmp_path: Path) -> None:
    result = _two_bar_ledger(tmp_path).validate_final_answer(
        "CW8.PA (yfinance, EUR) : −9,2 % depuis le plus haut."
        "\n\n```figures\n−9,2 % | derived | (650,30 − 716,25) / 716,25 | get_market_data\n```"
    )
    assert result.valid is False


# --- the omission note in French ---------------------------------------------------------
# The marker and the footnote were Chinese or English; a French answer ended with an
# English "※ 57 figure(s) ... were omitted" paragraph.


def _french_ledger(tmp_path: Path, message: str) -> GroundingLedger:
    ledger = GroundingLedger(run_dir=tmp_path, user_message=message)
    ledger.ingest_tool_result(
        tool_name="get_market_data",
        arguments={"codes": ["CW8.PA"]},
        result=json.dumps(
            {"CW8.PA": [{"trade_date": "2026-11-06T00:00:00", "open": 683.65, "high": 692.35,
                         "low": 682.91, "close": 692.3, "volume": 11736}]}
        ),
        call_id="prices",
        success=True,
    )
    return ledger


def test_a_french_request_gets_a_french_marker_and_note(tmp_path: Path) -> None:
    ledger = _french_ledger(tmp_path, "Aide moi à constituer mon portefeuille PEA, j'ai 3000 euros")
    draft = "CW8.PA (yfinance) a clôturé à 692,30 €. Prix d'entrée conseillé : 650,00 €."
    released = ledger.redacted_release(draft, ledger.validate_final_answer(draft))

    assert released is not None
    assert "Prix d'entrée conseillé : (omis※)." in released
    assert "692,30 €" in released
    assert "※ 1 chiffre(s) impossible(s) à rapprocher" in released
    assert "Plage OHLC observée : CW8.PA: 682.91–692.35 EUR" in released
    assert "aucune conversion de devise" in released
    assert "omitted" not in released


def test_an_english_request_keeps_the_english_note(tmp_path: Path) -> None:
    ledger = _french_ledger(tmp_path, "Build my portfolio with CW8.PA please")
    draft = "CW8.PA (yfinance) closed at 692.30 EUR. Suggested entry: 650.00 EUR."
    released = ledger.redacted_release(draft, ledger.validate_final_answer(draft))

    assert released is not None
    assert "Suggested entry: (omitted※)." in released
    assert "could not be matched" in released


def test_a_model_written_french_marker_is_stripped() -> None:
    from src.agent.grounding.release import _strip_release_markers

    assert _strip_release_markers("Prix (omis※) ici.\n※ note du modèle") == "Prix  ici."


def test_a_trailing_currency_symbol_is_cut_with_its_figure(tmp_path: Path) -> None:
    ledger = _french_ledger(tmp_path, "Build my portfolio with CW8.PA please")
    draft = "CW8.PA (yfinance) closed at 692.30 EUR. Suggested entry: 650.00 €."
    released = ledger.redacted_release(draft, ledger.validate_final_answer(draft))

    assert released is not None
    assert "Suggested entry: (omitted※)." in released


# --- index names -------------------------------------------------------------------------
# "PUST (Amundi Nasdaq-100)" was released as "Nasdaq-(omis※)": the number in an index
# name was read as an unmatched figure. "S&P 500" survived only when 500 was a price.


@pytest.mark.parametrize(
    "name",
    ["S&P 500", "Nasdaq-100", "Nasdaq 100", "Russell 2000", "Stoxx Europe 600", "Euro Stoxx 50",
     "CAC 40", "SBF 120", "FTSE 100", "Nikkei 225", "DAX 40", "沪深300"],
)
def test_the_number_in_an_index_name_is_not_a_figure(tmp_path: Path, name: str) -> None:
    result = _ledger(tmp_path, "CW8.PA", 692.3).validate_final_answer(
        f"| ETF | Indice |\n|---|---|\n| CW8.PA (yfinance) | ETF {name} |"
    )
    assert result.valid is True, result.issues


def test_a_price_written_after_an_index_name_is_still_checked(tmp_path: Path) -> None:
    result = _ledger(tmp_path, "CW8.PA", 692.3).validate_final_answer(
        "CW8.PA (yfinance, ETF S&P 500) a clôturé à 500,00 €."
    )
    assert result.valid is False
    assert "500,00" in [issue.get("claim") for issue in result.issues]
