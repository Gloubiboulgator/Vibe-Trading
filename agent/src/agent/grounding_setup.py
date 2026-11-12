"""Build a run's grounding ledger the one way the service does.

``AgentLoop`` and ``scripts/replay_grounding.py`` both call
:func:`build_grounding_ledger`. Two corrections once passed the replay and
failed in service, because the replay built its ledger by hand and missed what
the earlier turns of the session carry in (their evidence filled a quota; their
symbols were demanded by the provenance check). One construction point keeps
the replay from diverging again.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.agent.grounding import GroundingLedger
from src.agent.grounding.ledger import load_prior_evidence, load_prior_identities
from src.agent.pea_mode import PEA_SOURCE_ID, PEA_STANDING_MARKET


def earlier_session_runs(
    sessions_dir: Path,
    session_id: str,
    current_run_dir: Path,
    *,
    created_before: str | None = None,
) -> list[Path]:
    """Run directories of the session's earlier attempts, oldest first.

    Each attempt records the run it used; the current one is left out. An
    unreadable attempt is skipped: losing a carried identity only costs the
    model one more ``search_symbol``.

    Args:
        sessions_dir: Root of the stored sessions.
        session_id: Session whose attempts are read.
        current_run_dir: Run of the attempt being built, left out.
        created_before: Only attempts created strictly before this ISO time.
            The service never needs it (later attempts do not exist yet); a
            replay of a finished session does.

    Returns:
        Run directories ordered by attempt creation time.
    """
    if not session_id:
        return []
    attempts: list[tuple[str, Path]] = []
    for path in (Path(sessions_dir) / session_id / "attempts").glob("*/attempt.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        run_dir = data.get("run_dir") if isinstance(data, dict) else None
        if not run_dir or Path(run_dir) == Path(current_run_dir):
            continue
        created = str(data.get("created_at") or "")
        if created_before is not None and created >= created_before:
            continue
        attempts.append((created, Path(run_dir)))
    return [run_dir for _, run_dir in sorted(attempts)]


def build_grounding_ledger(
    *,
    run_dir: Path,
    user_message: str,
    history: Sequence[Mapping[str, Any]] | None,
    session_id: str,
    sessions_dir: Path,
    pea_mode: bool = False,
    contextual_identity_constraints: bool | None = None,
    created_before: str | None = None,
    ledger_cls: type[GroundingLedger] = GroundingLedger,
) -> GroundingLedger:
    """Create the ledger of one run, seeded with the session's earlier turns.

    Args:
        run_dir: Active run directory.
        user_message: Current user request, unwrapped.
        history: Message history the loop received.
        session_id: Owning session, empty for a session-less run.
        sessions_dir: Root of the stored sessions.
        pea_mode: The session invests through a French PEA.
        contextual_identity_constraints: Defaults to the runtime setting.
        created_before: See :func:`earlier_session_runs`.
        ledger_cls: The replay passes a subclass that never writes.

    Returns:
        The ledger the loop drives.
    """
    if contextual_identity_constraints is None:
        from src.config.accessor import get_env_config

        contextual_identity_constraints = (
            get_env_config().agent_tuning.vibe_contextual_identity_constraints
        )
    earlier_runs = earlier_session_runs(
        sessions_dir, session_id, run_dir, created_before=created_before
    )
    return ledger_cls(
        run_dir=run_dir,
        user_message=user_message,
        history=history,
        contextual_identity_constraints=contextual_identity_constraints,
        standing_markets=((PEA_STANDING_MARKET, PEA_SOURCE_ID),) if pea_mode else (),
        prior_identities=load_prior_identities(earlier_runs),
        prior_evidence=load_prior_evidence(earlier_runs),
    )
