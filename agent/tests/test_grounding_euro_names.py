"""Yahoo's spelling of a European name no longer hides its home listing (2026-11-09).

A PEA question on AI stocks resolved SAP SE to SAP.US and ASM International to
Vienna, and left Infineon, Siemens Energy and BESI ambiguous: "N.V." read as
two words, German listing names end in a padded share-class letter ("SAP SE
... I"), and "Infineon" is short for "Infineon Technologies". Every call on
the European line was then refused. The candidates are the resolver's answers
from that run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger

pytestmark = pytest.mark.unit

CANDIDATES = {
    "SAP SE": [
        {
            "symbol": "SAPH.US",
            "name": "SAP SE ADRhedged",
            "market": "us",
            "source": "eastmoney"
        },
        {
            "symbol": "SAP.US",
            "name": "SAP  SE",
            "market": "us",
            "exchange": "NYQ",
            "source": "yahoo",
            "cik": "0001000184"
        },
        {
            "symbol": "SAP.DE",
            "name": "SAP SE                        I",
            "market": "eu",
            "exchange": "GER",
            "source": "yahoo"
        },
        {
            "symbol": "SAP.F",
            "name": "SAP SE                        I",
            "market": "eu",
            "exchange": "FRA",
            "source": "yahoo"
        },
        {
            "symbol": "SAPD.XD",
            "name": "SAP SE",
            "market": "global",
            "exchange": "DXE",
            "source": "yahoo"
        }
    ],
    "ASM International": [
        {
            "symbol": "ASM.AS",
            "name": "ASM International N.V.",
            "market": "eu",
            "exchange": "AMS",
            "source": "yahoo"
        },
        {
            "symbol": "ASMIY.US",
            "name": "ASM International N.V.",
            "market": "us",
            "exchange": "OQX",
            "source": "yahoo"
        },
        {
            "symbol": "ASMI.VI",
            "name": "ASM INTERNATIONAL NV",
            "market": "eu",
            "exchange": "VIE",
            "source": "yahoo"
        },
        {
            "symbol": "AVS.F",
            "name": "ASM INTERNATIONAL N.V.        B",
            "market": "eu",
            "exchange": "FRA",
            "source": "yahoo"
        },
        {
            "symbol": "AVS.DE",
            "name": "ASM INTERNATIONAL N.V.        B",
            "market": "eu",
            "exchange": "GER",
            "source": "yahoo"
        }
    ],
    "Infineon": [
        {
            "symbol": "IFX.DE",
            "name": "INFINEON TECHNOLOGIES AG      N",
            "market": "eu",
            "exchange": "GER",
            "source": "yahoo"
        },
        {
            "symbol": "IFNNY.US",
            "name": "Infineon Technologies AG",
            "market": "us",
            "exchange": "OQX",
            "source": "yahoo",
            "cik": "0001107457"
        },
        {
            "symbol": "IFXA.HA",
            "name": "INFINEON TECHNOLOGIES AG      N",
            "market": "eu",
            "exchange": "HAN",
            "source": "yahoo"
        },
        {
            "symbol": "IFNNF.US",
            "name": "Infineon Technologies AG",
            "market": "us",
            "exchange": "OQX",
            "source": "yahoo",
            "cik": "0001107457"
        },
        {
            "symbol": "IFX.F",
            "name": "INFINEON TECHNOLOGIES AG      N",
            "market": "eu",
            "exchange": "FRA",
            "source": "yahoo"
        }
    ],
    "Siemens Energy": [
        {
            "symbol": "ENR.DE",
            "name": "Siemens Energy AG             N",
            "market": "eu",
            "exchange": "GER",
            "source": "yahoo"
        },
        {
            "symbol": "SMERY.US",
            "name": "Siemens Energy AG",
            "market": "us",
            "exchange": "OQX",
            "source": "yahoo",
            "cik": "0001830056"
        },
        {
            "symbol": "ENR.F",
            "name": "Siemens Energy AG             N",
            "market": "eu",
            "exchange": "FRA",
            "source": "yahoo"
        },
        {
            "symbol": "ENRIN.NS",
            "name": "SIEMENS ENERGY INDIA LTD",
            "market": "in",
            "exchange": "NSI",
            "source": "yahoo"
        },
        {
            "symbol": "SMEGF.US",
            "name": "Siemens Energy AG",
            "market": "us",
            "exchange": "OQX",
            "source": "yahoo",
            "cik": "0001830056"
        }
    ],
    "BE Semiconductor Industries": [
        {
            "symbol": "BESI.AS",
            "name": "BE Semiconductor Industries N.V",
            "market": "eu",
            "exchange": "AMS",
            "source": "yahoo"
        },
        {
            "symbol": "BESIY.US",
            "name": "BE Semiconductor Industries N.V",
            "market": "us",
            "exchange": "PNK",
            "source": "yahoo"
        },
        {
            "symbol": "BSI.DE",
            "name": "BE Semiconductor Inds N.V.    A",
            "market": "eu",
            "exchange": "GER",
            "source": "yahoo"
        },
        {
            "symbol": "BESVF.US",
            "name": "BE Semiconductor Industries N.V",
            "market": "us",
            "exchange": "PNK",
            "source": "yahoo"
        },
        {
            "symbol": "BSIA.F",
            "name": "BE SEMICONDUCTOR INDS N.V.    N",
            "market": "eu",
            "exchange": "FRA",
            "source": "yahoo"
        }
    ]
}

PEA = [("eu", "session:pea_mode")]


def _status(tmp_path: Path, query: str, candidates: list[dict]) -> tuple[str, str | None]:
    ledger = GroundingLedger(run_dir=tmp_path, user_message="Quelles actions IA ?", standing_markets=PEA)
    payload = {"ok": True, "source": "symbol_search", "data": {"query": query, "candidates": candidates}}
    ledger.ingest_tool_result(
        tool_name="search_symbol",
        arguments={"query": query},
        result=json.dumps(payload, ensure_ascii=False),
        call_id=f"resolve-{query}",
        success=True,
    )
    record = next(r for r in ledger.identity_summary()["records"] if r["query"] == query)
    return record["status"], record["symbol"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("SAP SE", "SAP.DE"),
        ("ASM International", "ASM.AS"),
        ("Infineon", "IFX.DE"),
        ("Siemens Energy", "ENR.DE"),
        ("BE Semiconductor Industries", "BESI.AS"),
    ],
)
def test_the_home_euro_listing_is_locked(tmp_path, query, expected) -> None:
    assert _status(tmp_path, query, CANDIDATES[query]) == ("locked", expected)


def test_a_short_name_never_borrows_another_company(tmp_path) -> None:
    """"Siemens" starts "Siemens Energy" too; the exact company wins."""
    candidates = [
        {"symbol": "SIE.DE", "name": "SIEMENS AG                    N", "market": "global", "exchange": "GER", "source": "yahoo"},
        {"symbol": "ENR.DE", "name": "Siemens Energy AG             N", "market": "global", "exchange": "GER", "source": "yahoo"},
    ]
    assert _status(tmp_path, "Siemens", candidates) == ("locked", "SIE.DE")


def test_a_short_name_shared_by_two_companies_stays_ambiguous(tmp_path) -> None:
    candidates = [
        {"symbol": "ENR.DE", "name": "Siemens Energy AG             N", "market": "global", "exchange": "GER", "source": "yahoo"},
        {"symbol": "SHL.DE", "name": "Siemens Healthineers AG       N", "market": "global", "exchange": "GER", "source": "yahoo"},
    ]
    assert _status(tmp_path, "Siemens", candidates)[0] == "ambiguous"
