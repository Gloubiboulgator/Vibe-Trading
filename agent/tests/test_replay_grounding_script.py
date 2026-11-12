"""The grounding replay builds its ledger as the service does, and triages refusals.

Two corrections once passed the replay and failed in service: the replay built
its ledger by hand, without the earlier turns' evidence and identities. Both
now go through ``build_grounding_ledger``. All values here are made up.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest

from src.agent import loop as loop_mod
from src.agent.grounding import GroundingLedger
from src.agent.grounding_setup import build_grounding_ledger, earlier_session_runs
from src.agent.pea_mode import PEA_STANDING_MARKET

pytestmark = pytest.mark.unit

_SPEC = importlib.util.spec_from_file_location(
    "replay_grounding", Path(__file__).resolve().parents[1] / "scripts" / "replay_grounding.py"
)
replay_grounding = importlib.util.module_from_spec(_SPEC)
sys.modules["replay_grounding"] = replay_grounding  # dataclasses look their module up
_SPEC.loader.exec_module(replay_grounding)

_FRENCH = "Pour répondre, voici ce que disent les données et ce que j'en déduis pour vous, chiffre par chiffre. "
_PAGE = json.dumps({"status": "ok", "url": "https://ipo.example.com/otherco", "content": (
    "Otherco priced its offering at $120 per share. The stock closed last week at $131.475."
)})


def _draft(prose: str, *lines: str) -> str:
    return f"{_FRENCH}{prose}\n\n```figures\n" + "\n".join(lines) + "\n```\n"


GOOD = _draft(
    "Introduite à 120 USD, l'action a clôturé à 131,475 USD, soit +9,6 %.",
    "120 | observed | prix d'introduction, USD | read_url",
    "131,475 | observed | dernière clôture, USD | read_url",
    "+9,6 % | derived | 131,475 / 120 − 1 | read_url",
)
WRONG = _draft(
    "Introduite à 120 USD, l'action a clôturé à 187,25 USD.",
    "120 | observed | prix d'introduction, USD | read_url",
    "187,25 | observed | dernière clôture, USD | read_url",
)


def _attempt(session: Path, attempt_id: str, created: str, run_dir: Path, prompt: str) -> None:
    folder = session / "attempts" / attempt_id
    folder.mkdir(parents=True)
    (folder / "attempt.json").write_text(json.dumps(
        {"attempt_id": attempt_id, "created_at": created, "run_dir": str(run_dir), "prompt": prompt}
    ))


def _corpus(tmp_path: Path) -> Path:
    """Two questions: the first reads a page, the second answers from it."""
    sessions = tmp_path / "sessions"
    session = sessions / "s1"
    session.mkdir(parents=True)
    first, second = tmp_path / "runs" / "r1", tmp_path / "runs" / "r2"
    # The service persisted the first run's evidence when it ran.
    ledger = GroundingLedger(run_dir=first, user_message="Une introduction en bourse ?")
    ledger.ingest_tool_result(tool_name="read_url", arguments={"url": "https://ipo.example.com/otherco"},
                              result=_PAGE, call_id="c1", success=True)
    _attempt(session, "a1", "2026-01-01T10:00:00+00:00", first, "Une introduction en bourse ?")
    _attempt(session, "a2", "2026-01-01T11:00:00+00:00", second, "Et depuis ?")
    events = [
        {"type": "start", "prompt": "Une introduction en bourse ?"},
        {"type": "tool_call", "call_id": "c1", "tool": "read_url", "args": {"url": "https://ipo.example.com/otherco"}},
        {"type": "tool_result", "call_id": "c1", "tool": "read_url", "result": _PAGE, "status": "ok"},
        {"type": "thinking", "content": GOOD},
        {"type": "start", "prompt": "Et depuis ?"},
        {"type": "thinking", "content": WRONG},
        {"type": "thinking", "content": GOOD},
    ]
    (session / "trace.jsonl").write_text("\n".join(json.dumps(event) for event in events) + "\n")
    return sessions


# ------------------------------------------------------------------ shared construction


def test_earlier_runs_are_ordered_and_skip_the_current_and_later_ones(tmp_path) -> None:
    session = tmp_path / "s1"
    for name, created in (("b", "2026-01-02"), ("a", "2026-01-01"), ("c", "2026-01-03")):
        _attempt(session, name, created, tmp_path / f"run-{name}", "?")
    assert earlier_session_runs(tmp_path, "s1", tmp_path / "run-c") == [tmp_path / "run-a", tmp_path / "run-b"]
    assert earlier_session_runs(tmp_path, "s1", tmp_path / "run-b", created_before="2026-01-02") == [
        tmp_path / "run-a"
    ]
    assert earlier_session_runs(tmp_path, "", tmp_path / "run-a") == []


def test_the_built_ledger_carries_earlier_turns_and_the_pea_market(tmp_path) -> None:
    sessions = _corpus(tmp_path)
    ledger = build_grounding_ledger(
        run_dir=tmp_path / "runs" / "r2", user_message="Et depuis ?", history=None,
        session_id="s1", sessions_dir=sessions, pea_mode=True, contextual_identity_constraints=True,
    )
    assert any(record.call_id == "c1" for record in ledger._evidence)
    assert PEA_STANDING_MARKET in str(ledger.resolution_context)
    assert ledger.validate_final_answer(GOOD).valid


def test_the_loop_builds_its_ledger_through_the_shared_function() -> None:
    source = inspect.getsource(loop_mod.AgentLoop)
    assert "build_grounding_ledger(" in source
    assert "GroundingLedger(" not in source


# ------------------------------------------------------------------ replay and baseline


def test_the_replay_runs_the_chain_per_question_without_writing(tmp_path) -> None:
    sessions = _corpus(tmp_path)
    before = sorted(path.name for path in tmp_path.rglob("*"))
    first, second = replay_grounding.replay_corpus(sessions)
    assert sorted(path.name for path in tmp_path.rglob("*")) == before
    assert (first.outcome, first.passing_draft) == ("passed", 1)
    assert (second.outcome, second.passing_draft) == ("passed", 2)
    assert [draft.valid for draft in second.drafts] == [False, True]


def test_the_baseline_keeps_counters_only_and_compare_reports_a_change(tmp_path) -> None:
    results = replay_grounding.replay_corpus(_corpus(tmp_path))
    data = replay_grounding.baseline(results)
    text = json.dumps(data)
    assert "187" not in text and "depuis" not in text and "Otherco" not in text
    assert replay_grounding.compare(data, data) == []
    changed = json.loads(text)
    changed["questions"][1]["passing_draft"] = None
    assert replay_grounding.compare(data, changed) == ["s1/a2: passing_draft None -> 2"]


def test_main_writes_then_compares_the_baseline(tmp_path, capsys) -> None:
    sessions, file = _corpus(tmp_path), tmp_path / "baseline.json"
    common = ["--sessions-dir", str(sessions), "--baseline", str(file)]
    assert replay_grounding.main([*common, "--write-baseline"]) == 0
    assert replay_grounding.main([*common, "--compare"]) == 0
    assert "0 écart(s)" in capsys.readouterr().out


# ------------------------------------------------------------------ triage


def test_a_written_number_reads_in_both_notations() -> None:
    assert {value for value, _, _ in replay_grounding.number_readings("1.234,5")} == {1234.5}
    assert {(value, kind) for value, _, kind in replay_grounding.number_readings("1,250")} == {
        (1250.0, ""), (1.25, "notation"),
    }


def test_the_pool_finds_a_value_in_another_scale_or_turn_only() -> None:
    pool = replay_grounding.EvidencePool([(2_340_000_000.0, "tour_precedent")], [48.125])
    assert pool.find("2,34") == "tour_precedent+notation+echelle"
    assert pool.find("48,125") == "texte_brut+notation"
    assert pool.find("91,7") is None
    assert pool.find("5") is None  # one digit never matches through a scale


def test_a_refusal_is_suspect_when_a_later_draft_passes_it_and_true_when_absent() -> None:
    draft = replay_grounding.DraftResult(1, False, False, [], {}, set())
    pool = replay_grounding.EvidencePool([], [])
    issue = {"code": "numeric_claim_unavailable", "reason": "no_evidence", "value": "63,4"}
    later = replay_grounding._judge(issue, draft, {63.4}, pool, 0, "s/a#1")
    absent = replay_grounding._judge(issue, draft, set(), pool, 0, "s/a#1")
    assert (later.suspect, later.why) == (True, "brouillon_suivant")
    assert (absent.suspect, absent.why) == (False, "absente")


def test_the_corpus_triage_marks_the_wrong_figure_true(tmp_path) -> None:
    results = replay_grounding.replay_corpus(_corpus(tmp_path))
    verdicts = replay_grounding.triage(results)
    assert verdicts and all(not verdict.suspect for verdict in verdicts)
    rows = replay_grounding.families_table(results, verdicts)
    assert rows[0]["true"] == len(verdicts) and rows[0]["example"] == "s1/a2#1"
