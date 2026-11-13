"""Runtime-written messages follow the user's language (2026-11-08 French audit).

The model answers in French on its own, but the texts the runtime writes itself
(empty, cancelled or failed run, tool stall, IM confirmation) were English only.
"""

from __future__ import annotations

import pytest

from src.agent.tool_progress import RECOVERY_MESSAGE, RECOVERY_MESSAGE_FR, ToolProgress
from src.agent.user_language import writes_french
from src.channels.runtime import _COMMIT_TOKENS, _DISCARD_TOKENS, _french_confirmation_card
from src.session.models import Attempt, AttemptStatus
from src.session.service import SessionService

pytestmark = pytest.mark.unit

FR = "Aide moi à constituer mon portefeuille PEA, j'ai 3000 euros"
EN = "Build my portfolio with CW8.PA please"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (FR, True), ("L'entreprise est-elle bien valorisée ?", True),
        ("Is the company fairly valued?", False), (EN, False),
        ("帮我分析 CW8.PA 的走势", False), ("", False), (None, False),
    ],
)
def test_writes_french(text, expected) -> None:
    assert writes_french(text) is expected


@pytest.mark.parametrize(
    ("status", "error", "fr", "en"),
    [
        (AttemptStatus.CANCELLED, None, "Exécution annulée.", "Run cancelled."),
        (AttemptStatus.FAILED, "timeout", "Échec de l'exécution : timeout", "Execution failed: timeout"),
        (AttemptStatus.COMPLETED, None, "L'exécution s'est terminée sans produire de texte", "The run finished"),
    ],
)
def test_result_message_follows_the_prompt_language(status, error, fr, en) -> None:
    def message(prompt: str) -> str:
        attempt = Attempt(prompt=prompt, status=status)
        attempt.error = error
        return SessionService._format_result_message(attempt)

    assert message(FR).startswith(fr)
    assert message(EN).startswith(en)


def test_stall_message_in_french() -> None:
    progress = ToolProgress()
    assert progress.recovery_message(french=True) == RECOVERY_MESSAGE_FR
    assert progress.recovery_message() == RECOVERY_MESSAGE
    progress.stalled_iterations = 8
    progress._stall_notes = [("error", "get_market_data", "rate_limited")] * 2
    message = progress.recovery_message(french=True)
    assert message.startswith("Je me suis arrêté, car 8 tours d'outils")
    assert "get_market_data a échoué (rate_limited) x2" in message


def test_french_confirmation_words_are_accepted() -> None:
    assert "confirmer" in _COMMIT_TOKENS and "confirm" in _COMMIT_TOKENS and "确认" in _COMMIT_TOKENS
    assert "annuler" in _DISCARD_TOKENS and "cancel" in _DISCARD_TOKENS and "取消" in _DISCARD_TOKENS
    card = _french_confirmation_card(
        "create",
        {"title": "Veille PEA"},
        {"expression": "0 8 * * 1-5", "timezone": "Europe/Paris"},
        {"channel": "email", "format": "pdf", "protect_pdf": True, "target_label": "moi"},
    )
    assert "Tâche : Veille PEA" in card
    assert "Protection du PDF par mot de passe : activée" in card
    assert "« confirmer »" in card and "« annuler »" in card
