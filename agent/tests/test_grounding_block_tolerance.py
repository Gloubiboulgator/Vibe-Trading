"""One odd declaration line no longer costs a French answer its whole block (2026-11-09).

A PEA analysis ended its block with ``2-3 | count | horizon en années``. The
line was unreadable, so the redacted release dropped the block and re-checked
every derived and profile figure as undeclared: 51 figures were masked. The
same block wrote ``5.051`` for a prose ``5,051``, read as five thousand
because the answer writes decimal commas.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.agent.grounding import GroundingLedger
from src.agent.grounding.figures import parse_figures_block

pytestmark = pytest.mark.unit

USER = "J'ai 3 000 euros à investir dans mon PEA, horizon 2-3 ans."
PROSE = "Votre budget de 3 000 € fixe la taille de chaque ligne.\n\n"


def _ledger() -> GroundingLedger:
    return GroundingLedger(run_dir=Path(tempfile.mkdtemp()), user_message=USER)


def test_a_bare_range_is_two_declarations() -> None:
    block = parse_figures_block("```figures\n2-3 | count | horizon en années | utilisateur\n```")
    assert block.malformed == ()
    assert [d.value for d in block.declarations] == [2.0, 3.0]


def test_a_dated_value_is_still_not_a_range() -> None:
    block = parse_figures_block("```figures\n2026-11-09 | count | date\n```")
    assert block.declarations == ()
    assert len(block.malformed) == 1


def test_a_point_written_block_in_a_french_answer_keeps_its_decimals() -> None:
    content = (
        "La marge atteint 19,6 %. Le multiple est de 5,051.\n\n"
        "```figures\n71.14 | observed | close\n5.051 | observed | EV/EBITDA\n```"
    )
    assert [d.value for d in parse_figures_block(content).declarations] == [71.14, 5.051]


def test_a_comma_in_the_block_leaves_the_document_reading() -> None:
    content = (
        "La marge atteint 19,6 %. Le total est 5.051.\n\n"
        "```figures\n19,6% | observed | marge\n5.051 | observed | total\n```"
    )
    assert [d.value for d in parse_figures_block(content).declarations] == [19.6, 5051.0]


def test_the_redaction_keeps_the_readable_declarations() -> None:
    ledger = _ledger()
    draft = PROSE + (
        "```figures\n"
        "3000 | cited | budget indiqué par vous | utilisateur\n"
        "deux à trois | count | horizon\n"
        "```"
    )
    validation = ledger.validate_final_answer(draft)
    assert {issue.get("reason") for issue in validation.issues} == {"unparseable_declaration"}
    released = ledger.redacted_release(draft, validation)
    assert released is not None
    assert "omis" not in released
    assert "3 000 €" in released
