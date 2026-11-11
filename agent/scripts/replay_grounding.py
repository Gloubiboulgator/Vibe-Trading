"""Replay stored answer drafts against the current grounding gate.

Every session trace keeps the drafts the gate rejected, and each run keeps the
evidence its tools returned. This script checks those drafts again with the
code as it is now, without calling any model or data provider, so a fix to the
gate can be measured on every past answer instead of one reported case.

By default only the drafts that reached the user with figures omitted are
replayed (a rejected draft followed by a redacted release). ``--all`` replays
every rejected draft, including the intermediate ones the user never saw.

A run stored before evidence carried its currency cannot be judged: a figure
written with "€" only matches evidence of that currency. Such drafts are
listed as not judged rather than counted as failures.

Usage, from ``agent/``::

    python scripts/replay_grounding.py              # released answers only
    python scripts/replay_grounding.py --all        # every rejected draft
    python scripts/replay_grounding.py --session bfe957b59903 -v

Exit status is 1 when a judged released answer still has an issue.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.grounding import GroundingLedger  # noqa: E402
from src.agent.grounding.evidence import EvidenceRecord  # noqa: E402
from src.agent.grounding.ledger import GROUNDING_ARTIFACT  # noqa: E402
from src.config.paths import get_sessions_dir  # noqa: E402

_RECORD_FIELDS = {item.name for item in fields(EvidenceRecord)}


@dataclass
class Draft:
    """One stored draft and the run whose evidence it was checked against."""

    session: str
    line: int
    prompt: str
    content: str
    run_dir: Path | None
    released: bool
    issues: list[dict[str, Any]] = field(default_factory=list)
    judged: bool = True
    note: str = ""


def _events(trace: Path) -> list[dict[str, Any]]:
    events = []
    for raw in trace.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(raw))
        except ValueError:
            events.append({})
    return events


def iter_drafts(sessions_dir: Path, *, only: str | None, include_all: bool) -> Iterator[Draft]:
    """Yield the stored drafts of every session, oldest line first."""
    for trace in sorted(sessions_dir.glob("*/trace.jsonl")):
        session = trace.parent.name
        if only and not session.startswith(only):
            continue
        events = _events(trace)
        released_lines = set()
        for index, event in enumerate(events):
            if event.get("type") == "answer_released_redacted":
                for back in range(index - 1, -1, -1):
                    if events[back].get("type") == "answer_rejected":
                        released_lines.add(back)
                        break
        prompt = ""
        run_dir: Path | None = None
        for index, event in enumerate(events):
            kind = event.get("type")
            if kind == "start":
                prompt, run_dir = str(event.get("prompt") or ""), None
            args = event.get("args")
            if isinstance(args, dict) and args.get("run_dir"):
                run_dir = Path(str(args["run_dir"]))
            if kind != "answer_rejected" or not event.get("content"):
                continue
            released = index in released_lines
            if released or include_all:
                yield Draft(session, index, prompt, str(event["content"]), run_dir, released)


def replay(draft: Draft) -> Draft:
    """Validate one draft against its run's stored evidence."""
    artifact = draft.run_dir / "artifacts" / GROUNDING_ARTIFACT if draft.run_dir else None
    if artifact is None or not artifact.exists():
        draft.judged, draft.note = False, "no stored evidence for this run"
        return draft
    stored = json.loads(artifact.read_text(encoding="utf-8"))
    records = [
        EvidenceRecord(**{key: value for key, value in raw.items() if key in _RECORD_FIELDS})
        for raw in stored.get("evidence") or []
    ]
    priced = [record for record in records if record.tool == "get_market_data"]
    if priced and all(record.currency is None for record in priced):
        draft.judged, draft.note = False, "evidence stored before currencies were recorded"
        return draft
    ledger = GroundingLedger(run_dir=Path(tempfile.mkdtemp()), user_message=draft.prompt)
    ledger._evidence = records
    ledger._analysis_metrics = list(stored.get("analysis_evidence") or [])
    ledger._session_symbols |= set(stored.get("session_symbols") or [])
    ledger._session_symbol_roots |= set(stored.get("session_symbol_roots") or [])
    try:
        draft.issues = list(ledger.validate_final_answer(draft.content).issues)
    except Exception as exc:  # noqa: BLE001 - a crash is itself a finding
        draft.issues = [{"reason": "replay_crash", "claim": "", "message": f"{type(exc).__name__}: {exc}"}]
    return draft


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--all", action="store_true", help="replay every rejected draft, not only released ones")
    parser.add_argument("--session", help="only sessions whose id starts with this")
    parser.add_argument("-v", "--verbose", action="store_true", help="print every remaining issue")
    parser.add_argument("--sessions-dir", type=Path, default=None, help="defaults to the runtime sessions dir")
    args = parser.parse_args(argv)

    drafts = [
        replay(draft)
        for draft in iter_drafts(
            args.sessions_dir or get_sessions_dir(), only=args.session, include_all=args.all
        )
    ]
    reasons: Counter[str] = Counter()
    failing_released = 0
    for draft in drafts:
        label = "released" if draft.released else "draft"
        head = f"{draft.session} line {draft.line} [{label}] {draft.prompt[:60]!r}"
        if not draft.judged:
            print(f"{head}: not judged ({draft.note})")
            continue
        reasons.update(str(issue.get("reason") or issue.get("code")) for issue in draft.issues)
        if draft.released and draft.issues:
            failing_released += 1
        print(f"{head}: {len(draft.issues)} issue(s)")
        if args.verbose:
            for issue in draft.issues:
                print(f"    {issue.get('claim') or issue.get('value')!s:>14} | {issue.get('reason')} | "
                      f"{str(issue.get('message') or '')[:140]}")
    judged = [draft for draft in drafts if draft.judged]
    print()
    print(f"{len(drafts)} draft(s), {len(judged)} judged, "
          f"{sum(1 for draft in judged if not draft.issues)} clean")
    for reason, count in reasons.most_common():
        print(f"  {count:5d}  {reason}")
    return 1 if failing_released else 0


if __name__ == "__main__":
    sys.exit(main())
