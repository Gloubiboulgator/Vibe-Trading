"""A chosen percent declared bare with "%" in its note grounds the "20 %" in the prose (2026-11-09).

The agent asked a PEA user how large a drop they would sit through, offering
"environ 20 %, environ 35 %" as illustrations. It declared them
``20 | count | repère ... (%)``: the sign sat in the note, not the value, so
both figures were undeclared and the released question read "environ (omis※)".
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger

pytestmark = pytest.mark.unit

USER = "J'ai 3 000 euros à investir dans mon PEA. Pose-moi 3 questions."
QUESTION = (
    "Quelle baisse temporaire de votre budget de 3 000 € resteriez-vous prêt à encaisser "
    "sans vendre ? Je propose trois repères d'illustration : environ 20 %, environ 35 %, "
    "ou davantage.\n\n"
)


def _issues(block: str) -> list[tuple[str, str]]:
    ledger = GroundingLedger(run_dir=Path(tempfile.mkdtemp()), user_message=USER)
    result = ledger.validate_final_answer(QUESTION + "```figures\n" + block + "\n```")
    return [(issue.get("claim"), issue.get("reason")) for issue in result.issues]


def test_the_trace_declaration_now_passes() -> None:
    assert _issues(
        "3 000 | cited | budget indiqué par vous (montant à investir dans le PEA) | utilisateur\n"
        "20 | count | repère de baisse temporaire illustratif (%)\n"
        "35 | count | repère de baisse temporaire illustratif (%)"
    ) == []


def test_a_bare_count_without_a_percent_note_still_does_not_cover_a_percent() -> None:
    issues = _issues(
        "3 000 | cited | budget indiqué par vous | utilisateur\n"
        "20 | count | repère de baisse\n"
        "35 | count | repère de baisse"
    )
    assert {claim for claim, _ in issues} == {"20 %", "35 %"}


def test_only_a_count_may_borrow_the_sign() -> None:
    issues = _issues(
        "3 000 | cited | budget indiqué par vous | utilisateur\n"
        "20 | observed | baisse (%)\n"
        "35 | count | repère de baisse (%)"
    )
    assert [claim for claim, _ in issues] == ["20 %"]
