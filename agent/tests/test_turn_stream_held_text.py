"""Answer text held back for the figure check still keeps the page alive (2026-11-12).

A grounded turn buffers the answer until the gate has read it. While the
model wrote for 115 s nothing reached the page, which gave up after its
90 s SSE timeout and showed "Attente interrompue" over a run that went on.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.agent.loop_streaming import TurnStream

pytestmark = pytest.mark.unit


def _stream(events: list[tuple[str, dict]], interval: float) -> TurnStream:
    grounding = SimpleNamespace(should_buffer_output=True)
    return TurnStream(
        grounding=grounding,  # type: ignore[arg-type]
        emit=lambda kind, data: events.append((kind, data)),
        iteration=3,
        heartbeat_interval=lambda: interval,
        reasoning_interval=lambda: 1.0,
    )


def test_buffered_text_emits_a_waiting_heartbeat_and_no_text() -> None:
    events: list[tuple[str, dict]] = []
    stream = _stream(events, interval=0.0)
    stream.on_text("ASML.AS cote 1403.80 EUR.")
    stream.on_text(" Suite du texte.")
    assert [kind for kind, _ in events] == ["llm_waiting", "llm_waiting"]
    assert all(data == {"iter": 3} for _, data in events)


def test_the_heartbeat_is_throttled() -> None:
    events: list[tuple[str, dict]] = []
    stream = _stream(events, interval=3600.0)
    for _ in range(50):
        stream.on_text("mot ")
    assert [kind for kind, _ in events] == ["llm_waiting"]
