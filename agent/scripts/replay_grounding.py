"""Replay every stored answer draft through the grounding gate, as the service runs it.

Each question of a session (a ``start`` entry of its ``trace.jsonl``) is
replayed on a ledger built by the same function ``AgentLoop`` uses
(:func:`src.agent.grounding_setup.build_grounding_ledger`): earlier turns'
identities and evidence, the history the service passed, the PEA setting. The
question's tool results are re-ingested in trace order, and each draft (a
``thinking`` entry carrying a figures block) goes through the service's chain:
validation, provenance repair, recovery, revision budget, then redacted
release or the deterministic fallback. Nothing calls a model or a data
provider, and nothing is written into a session or a run.

Output is a short summary: one line per refusal family (code/reason) with its
triage. A refusal is *suspect* (a probable false refusal) when its value exists
in the session's evidence under some form (other notation, other scale, other
tool, an earlier turn, a raw tool result) or when a later draft of the same
question gets the same value through; it is *true* otherwise.

The baseline file keeps only codes, reasons, counters and session/attempt ids,
never a value or a draft text.

Usage, from ``agent/``::

    python scripts/replay_grounding.py                    # families
    python scripts/replay_grounding.py --write-baseline   # refresh the baseline
    python scripts/replay_grounding.py --compare          # differences with it

Exit status is 1 when ``--compare`` finds a difference.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.grounding import GroundingLedger, ValidationResult  # noqa: E402
from src.agent.grounding.release import MAX_GROUNDING_REVISIONS  # noqa: E402
from src.agent.grounding_setup import build_grounding_ledger  # noqa: E402
from src.agent.tool_results import _is_tool_success, _normalize_tool_run_dir  # noqa: E402
from src.agent.trace import TraceWriter  # noqa: E402
from src.config.paths import get_sessions_dir  # noqa: E402
from src.session.models import Message  # noqa: E402
from src.session.service import SessionService  # noqa: E402

BASELINE = Path(__file__).resolve().with_name("grounding_baseline.json")
_FIGURES_FENCE = "```figures"
_HISTORY_LIMIT = 100  # SessionStore.get_messages default
_SCALES = {1.0: "", 1e2: "echelle", 1e-2: "echelle", 1e3: "echelle", 1e-3: "echelle",
           1e6: "echelle", 1e-6: "echelle", 1e9: "echelle", 1e-9: "echelle"}
_RAW_NUMBER_RE = re.compile(r"-?\d[\d.,   ]*\d|-?\d")


class ReplayLedger(GroundingLedger):
    """The service's ledger, minus the write: a replay never touches a run."""

    def persist(self) -> None:  # noqa: D102 - see class docstring
        return None


@dataclass
class DraftResult:
    """The gate's verdict on one stored draft (no text kept beyond the run)."""

    index: int
    valid: bool
    repaired: bool
    issues: list[dict[str, Any]]
    figures: dict[tuple[int, int], Any]
    passed_values: set[float]


@dataclass
class QuestionResult:
    """One question (``start`` entry) and how the service chain ends for it."""

    session: str
    attempt: str
    drafts: list[DraftResult] = field(default_factory=list)
    passing_draft: int | None = None
    outcome: str = "no_draft"
    figures_removed: int = 0
    final_draft: int | None = None
    evidence_values: list[tuple[float, bool]] = field(default_factory=list)
    raw_text: list[str] = field(default_factory=list)
    error: str = ""


# --------------------------------------------------------------------------- corpus


def _attempts(session_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in (session_dir / "attempts").glob("*/attempt.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            rows.append(data)
    return sorted(rows, key=lambda row: str(row.get("created_at") or ""))


def _epoch(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        return None


def _history(session_dir: Path, attempt: dict[str, Any]) -> list[dict[str, Any]] | None:
    """The history the service passed: messages stored when the attempt started."""
    path = session_dir / "messages.jsonl"
    cutoff = _epoch(attempt.get("started_at")) or _epoch(attempt.get("created_at"))
    if not path.exists() or cutoff is None:
        return None
    messages = []
    for raw in path.read_text(encoding="utf-8").split("\n"):
        try:
            message = Message.from_dict(json.loads(raw))
        except (ValueError, TypeError, AttributeError):
            continue
        created = _epoch(message.created_at)
        if created is not None and created <= cutoff:
            messages.append(message)
    messages = messages[-_HISTORY_LIMIT:]
    return SessionService._convert_messages_to_history(messages) if messages else None


def _pea_mode(session_dir: Path) -> bool:
    try:
        data = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool((data.get("config") or {}).get("pea_mode"))


def _segments(events: list[dict[str, Any]]) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
    start: dict[str, Any] | None = None
    body: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") == "start":
            if start is not None:
                yield start, body
            start, body = event, []
        elif start is not None:
            body.append(event)
    if start is not None:
        yield start, body


def _match_attempts(
    starts: list[dict[str, Any]], attempts: list[dict[str, Any]]
) -> list[dict[str, Any] | None]:
    """Pair each ``start`` with its attempt: same prompt, in order."""
    matched: list[dict[str, Any] | None] = []
    cursor = 0
    for start in starts:
        found = None
        for index in range(cursor, len(attempts)):
            if str(attempts[index].get("prompt") or "") == str(start.get("prompt") or ""):
                found, cursor = attempts[index], index + 1
                break
        matched.append(found)
    return matched


# --------------------------------------------------------------------------- replay


def _release(ledger: GroundingLedger, content: str, validation: ValidationResult, result: QuestionResult) -> None:
    released = ledger.redacted_release(content, validation)
    if released is not None:
        result.outcome, result.figures_removed = "redacted", ledger.figures_removed
    else:
        ledger.safe_fallback()
        result.outcome = "fallback"


def replay_question(
    sessions_dir: Path,
    session_dir: Path,
    start: dict[str, Any],
    body: list[dict[str, Any]],
    attempt: dict[str, Any],
) -> QuestionResult:
    """Replay one question through the service's chain."""
    result = QuestionResult(session_dir.name, str(attempt.get("attempt_id") or ""))
    run_dir = Path(str(attempt["run_dir"]))
    ledger = build_grounding_ledger(
        run_dir=run_dir,
        user_message=str(start.get("prompt") or attempt.get("prompt") or ""),
        history=_history(session_dir, attempt),
        session_id=session_dir.name,
        sessions_dir=sessions_dir,
        pea_mode=_pea_mode(session_dir),
        created_before=str(attempt.get("created_at") or ""),
        ledger_cls=ReplayLedger,
    )
    arguments: dict[str, dict[str, Any]] = {}
    revisions = 0
    last: tuple[str, ValidationResult, int] | None = None
    for event in body:
        kind = event.get("type")
        if kind == "tool_call" and isinstance(event.get("args"), dict):
            arguments[str(event.get("call_id"))] = event["args"]
        elif kind == "tool_result" and isinstance(event.get("result"), str):
            call_id = str(event.get("call_id"))
            text = event["result"]
            result.raw_text.append(text)
            ledger.ingest_tool_result(
                tool_name=str(event.get("tool") or ""),
                arguments=_normalize_tool_run_dir(dict(arguments.get(call_id) or {}), str(run_dir)),
                result=text,
                call_id=call_id,
                success=_is_tool_success(text),
            )
        elif kind == "thinking" and _FIGURES_FENCE in str(event.get("content") or ""):
            content = str(event["content"])
            validation = ledger.validate_final_answer(content)
            figures = {(f.start, f.end): f for f in ledger._active_figures}
            draft = DraftResult(
                index=len(result.drafts) + 1,
                valid=validation.valid,
                repaired=False,
                issues=list(validation.issues),
                figures=figures,
                passed_values={
                    f.value for f in figures.values() if f.text in set(validation.passed_figures)
                },
            )
            result.drafts.append(draft)
            if not validation.valid:
                repaired = ledger.repair_provenance(content, validation)
                if repaired is not None:
                    recheck = ledger.revalidate(repaired)
                    if recheck.valid:
                        validation, draft.repaired = recheck, True
            if result.outcome != "no_draft":
                continue  # the service stopped here; later drafts only count refusals
            if validation.valid:
                result.outcome, result.passing_draft = "passed", draft.index
                result.final_draft = draft.index
                continue
            last = (content, validation, draft.index)
            recovery = ledger.recovery_action(validation)
            if recovery is not None:
                ledger.record_recovery(recovery)
                continue
            revisions += 1
            if revisions >= MAX_GROUNDING_REVISIONS:
                _release(ledger, content, validation, result)
                result.final_draft = draft.index
    if result.outcome == "no_draft" and last is not None:
        # The trace ran out of drafts before the cap: release the last one
        # as the service does at the cap.
        _release(ledger, last[0], last[1], result)
        result.final_draft = last[2]
    prior = ledger._prior_calls
    result.evidence_values = [
        (float(record.value), record.call_id in prior)
        for record in ledger._evidence
        if isinstance(record.value, (int, float)) and not isinstance(record.value, bool)
        and math.isfinite(float(record.value))
    ]
    return result


def replay_corpus(sessions_dir: Path, only: str | None = None) -> list[QuestionResult]:
    """Replay every question of every session that has at least one draft."""
    results: list[QuestionResult] = []
    for trace in sorted(sessions_dir.glob("*/trace.jsonl")):
        session_dir = trace.parent
        if only and not session_dir.name.startswith(only):
            continue
        events = TraceWriter.read(session_dir, resolve_offloads=True)
        segments = list(_segments(events))
        attempts = _match_attempts([start for start, _ in segments], _attempts(session_dir))
        for (start, body), attempt in zip(segments, attempts):
            if not any(
                e.get("type") == "thinking" and _FIGURES_FENCE in str(e.get("content") or "") for e in body
            ):
                continue
            if attempt is None or not attempt.get("run_dir"):
                results.append(QuestionResult(session_dir.name, "", outcome="not_judged", error="no_attempt"))
                continue
            try:
                results.append(replay_question(sessions_dir, session_dir, start, body, attempt))
            except Exception as exc:  # noqa: BLE001 - a crash is itself a finding
                results.append(QuestionResult(
                    session_dir.name, str(attempt.get("attempt_id") or ""),
                    outcome="crash", error=type(exc).__name__,
                ))
    return results


# --------------------------------------------------------------------------- baseline


def family(issue: dict[str, Any]) -> str:
    return f"{issue.get('code')}/{issue.get('reason')}"


def baseline(results: Iterable[QuestionResult]) -> dict[str, Any]:
    """Codes, reasons, counters and ids only: no value, no draft text."""
    return {
        "version": 1,
        "questions": [
            {
                "session": r.session,
                "attempt": r.attempt,
                "outcome": r.outcome,
                "passing_draft": r.passing_draft,
                "figures_removed": r.figures_removed,
                "error": r.error,
                "drafts": [
                    {
                        "draft": d.index,
                        "valid": d.valid,
                        "repaired": d.repaired,
                        "refusals": dict(sorted(Counter(family(i) for i in d.issues).items())),
                    }
                    for d in r.drafts
                ],
            }
            for r in results
        ],
    }


def compare(current: dict[str, Any], reference: dict[str, Any]) -> list[str]:
    """One short line per difference, keyed by session/attempt/draft."""
    def index(data: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
        return {(q["session"], q["attempt"]): q for q in data.get("questions") or []}

    now, ref = index(current), index(reference)
    lines: list[str] = []
    for key in sorted(ref.keys() - now.keys()):
        lines.append(f"{key[0]}/{key[1]}: question absente du rejeu")
    for key in sorted(now.keys() - ref.keys()):
        lines.append(f"{key[0]}/{key[1]}: nouvelle question ({now[key]['outcome']})")
    for key in sorted(now.keys() & ref.keys()):
        a, b = ref[key], now[key]
        tag = f"{key[0]}/{key[1]}"
        for name in ("outcome", "passing_draft", "figures_removed", "error"):
            if a.get(name) != b.get(name):
                lines.append(f"{tag}: {name} {a.get(name)} -> {b.get(name)}")
        old = {d["draft"]: d for d in a.get("drafts") or []}
        new = {d["draft"]: d for d in b.get("drafts") or []}
        for number in sorted(old.keys() | new.keys()):
            before = Counter((old.get(number) or {}).get("refusals") or {})
            after = Counter((new.get(number) or {}).get("refusals") or {})
            for fam in sorted(before.keys() | after.keys()):
                if before[fam] != after[fam]:
                    lines.append(f"{tag}#{number}: {fam} {before[fam]} -> {after[fam]}")
    return lines


# --------------------------------------------------------------------------- triage


def number_readings(text: str) -> set[tuple[float, int, str]]:
    """Every (value, decimals, kind) a written number can mean.

    ``kind`` is "" for the reading with ``.`` as decimal point and
    ``notation`` for the other convention (French ``,`` decimal, ``.``
    thousands). Spaces of any width are thousands separators.
    """
    digits = re.sub(r"[^\d.,-]", "", text.replace("−", "-"))
    if not re.search(r"\d", digits):
        return set()
    readings: set[tuple[float, int, str]] = set()
    conventions = [(".", ",", ""), (",", ".", "notation")]
    if "," in digits and "." in digits:
        # Both marks: the last one is the decimal point, whatever the language.
        conventions = [c for c in conventions if c[0] == max(",.", key=digits.rfind)]
    for decimal, thousands, kind in conventions:
        body = digits.replace(thousands, "")
        if body.count(decimal) > 1:
            continue
        body = body.replace(decimal, ".")
        try:
            value = float(body)
        except ValueError:
            continue
        places = len(body.split(".")[1]) if "." in body else 0
        readings.add((value, places, kind))
    default = {value for value, _, kind in readings if kind == ""}
    return {item for item in readings if item[2] == "" or item[0] not in default}


def _significant(text: str) -> int:
    return len(re.sub(r"\D", "", text).lstrip("0"))


class EvidencePool:
    """Every number a session's evidence and tool results hold, rounding-indexed."""

    def __init__(self, structured: Iterable[tuple[float, str]], raw: Iterable[float]) -> None:
        self._structured = list(structured)
        self._raw = list(raw)
        self._cache: dict[tuple[str, float, int], dict[float, str]] = {}

    def _index(self, pool: str, scale: float, places: int) -> dict[float, str]:
        key = (pool, scale, places)
        if key not in self._cache:
            source = self._structured if pool == "structured" else [(v, "texte_brut") for v in self._raw]
            table: dict[float, str] = {}
            for value, origin in source:
                table.setdefault(round(value / scale, places), origin)
            self._cache[key] = table
        return self._cache[key]

    def find(self, text: str, extra: Iterable[float] = ()) -> str | None:
        """The first kind of match for a written figure, or None."""
        readings = number_readings(text) | {(value, 9, "") for value in extra}
        for pool in ("structured", "raw"):
            if pool == "raw" and _significant(text) < 3:
                break
            for scale, scale_kind in _SCALES.items():
                if scale != 1.0 and _significant(text) < 2:
                    continue  # "5" reads as 5 k, 5 M... of anything
                for value, places, kind in sorted(readings, key=lambda r: r[2] != ""):
                    hit = self._index(pool, scale, min(places, 9)).get(round(value, min(places, 9)))
                    if hit is not None:
                        return "+".join(part for part in (hit, kind, scale_kind) if part)
        return None


def _raw_numbers(texts: Iterable[str]) -> Iterator[float]:
    for text in texts:
        for token in _RAW_NUMBER_RE.findall(text):
            for value, _, _ in number_readings(token):
                if math.isfinite(value):
                    yield value


@dataclass
class Verdict:
    family: str
    suspect: bool
    why: str
    ref: str


def triage(results: list[QuestionResult]) -> list[Verdict]:
    """Mark each refusal suspect (value found elsewhere) or true."""
    by_session: dict[str, list[QuestionResult]] = {}
    for result in results:
        by_session.setdefault(result.session, []).append(result)
    verdicts: list[Verdict] = []
    for session, questions in by_session.items():
        structured: list[tuple[float, str]] = []
        for position, question in enumerate(questions):
            for value, carried in question.evidence_values:
                structured.append((value, "tour_precedent" if carried else f"preuve@{position}"))
        pool = EvidencePool(structured, _raw_numbers(text for q in questions for text in q.raw_text))
        for position, question in enumerate(questions):
            for draft in question.drafts:
                later = set().union(*(d.passed_values for d in question.drafts if d.index > draft.index)) \
                    if draft.index < len(question.drafts) else set()
                ref = f"{session}/{question.attempt}#{draft.index}"
                for issue in draft.issues:
                    verdicts.append(_judge(issue, draft, later, pool, position, ref))
    return verdicts


def _judge(
    issue: dict[str, Any], draft: DraftResult, later: set[float], pool: EvidencePool, position: int, ref: str
) -> Verdict:
    text = issue.get("value")
    if not isinstance(text, str) or not re.search(r"\d", text):
        return Verdict(family(issue), False, "sans_valeur", ref)
    span = issue.get("span")
    figure = draft.figures.get(tuple(span)) if isinstance(span, (list, tuple)) and len(span) == 2 else None
    exact = {figure.value} if figure is not None else set()
    if exact & later or any(value in later for value, _, _ in number_readings(text)):
        return Verdict(family(issue), True, "brouillon_suivant", ref)
    hit = pool.find(text, exact)
    if hit is None:
        return Verdict(family(issue), False, "absente", ref)
    hit = hit.replace(f"preuve@{position}", "preuve")
    hit = re.sub(r"preuve@\d+", "autre_question", hit)
    return Verdict(family(issue), True, hit, ref)


# --------------------------------------------------------------------------- report


def families_table(results: list[QuestionResult], verdicts: list[Verdict]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}

    def row(name: str) -> dict[str, Any]:
        return rows.setdefault(name, {"family": name, "refusals": 0, "suspects": 0, "true": 0,
                                      "removed": 0, "fallbacks": 0, "example": "", "why": Counter()})

    for verdict in verdicts:
        current = row(verdict.family)
        current["refusals"] += 1
        current["suspects" if verdict.suspect else "true"] += 1
        if verdict.suspect:
            current["why"][verdict.why] += 1
        if not current["example"] or (verdict.suspect and not current.get("example_suspect")):
            current["example"], current["example_suspect"] = verdict.ref, verdict.suspect
    for result in results:
        final = next((d for d in result.drafts if d.index == result.final_draft), None)
        if final is None:
            continue
        if result.outcome == "redacted":
            for issue in final.issues:
                row(family(issue))["removed"] += 1
        elif result.outcome == "fallback":
            for name in {family(issue) for issue in final.issues}:
                row(name)["fallbacks"] += 1
    return sorted(rows.values(), key=lambda r: (-r["removed"], -r["fallbacks"], -r["refusals"], r["family"]))


def print_report(results: list[QuestionResult], verdicts: list[Verdict]) -> None:
    outcomes = Counter(r.outcome for r in results)
    drafts = sum(len(r.drafts) for r in results)
    print(f"{len(results)} question(s), {drafts} brouillon(s) ; "
          + ", ".join(f"{name} {count}" for name, count in sorted(outcomes.items()))
          + f" ; chiffres retirés {sum(r.figures_removed for r in results)}")
    print(f"{'famille':52} {'refus':>5} {'susp':>5} {'vrais':>5} {'retir':>5} {'secours':>7}  exemple / motif")
    for current in families_table(results, verdicts):
        why = ",".join(name for name, _ in current["why"].most_common(2))
        print(f"{current['family'][:52]:52} {current['refusals']:5d} {current['suspects']:5d} "
              f"{current['true']:5d} {current['removed']:5d} {current['fallbacks']:7d}  "
              f"{current['example']} {why}".rstrip())
    crashed = [r for r in results if r.outcome in {"crash", "not_judged"}]
    for result in crashed[:10]:
        print(f"  {result.outcome}: {result.session}/{result.attempt} {result.error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--session", help="only sessions whose id starts with this")
    parser.add_argument("--sessions-dir", type=Path, default=None, help="defaults to the runtime sessions dir")
    parser.add_argument("--baseline", type=Path, default=BASELINE, help="baseline file")
    parser.add_argument("--write-baseline", action="store_true", help="write the baseline file")
    parser.add_argument("--compare", action="store_true", help="report differences with the baseline")
    parser.add_argument("--max-lines", type=int, default=40, help="cap on printed differences")
    args = parser.parse_args(argv)

    results = replay_corpus(args.sessions_dir or get_sessions_dir(), only=args.session)
    print_report(results, triage(results))
    current = baseline(results)
    status = 0
    if args.compare:
        reference = json.loads(args.baseline.read_text(encoding="utf-8"))
        lines = compare(current, reference)
        for line in lines[: args.max_lines]:
            print(line)
        print(f"{len(lines)} écart(s) avec {args.baseline.name}")
        status = 1 if lines else 0
    if args.write_baseline:
        args.baseline.write_text(json.dumps(current, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"bilan écrit : {args.baseline}")
    return status


if __name__ == "__main__":
    sys.exit(main())
