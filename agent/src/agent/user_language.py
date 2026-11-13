"""Which language the user writes, for the canned messages the runtime shows them.

The model answers in the user's language on its own; the texts the runtime writes
itself (stop notices, grounding notes, failure replies) do not, so a French user read
English boilerplate at the end of a run. These helpers pick the language from the
user's own message, never from the model's draft.
"""

from __future__ import annotations

import re

# Words a French request uses and an English or Spanish one does not. Two of them
# make the canned text French; one could be a loanword.
FRENCH_WORDS = frozenset(
    {
        "je", "j'ai", "j’ai", "les", "des", "est", "une", "pour", "mon", "mes",
        "avec", "dans", "veux", "vous", "nous", "c'est", "c’est", "quelles", "quel",
        "moi", "suis", "sur", "aide", "acheter", "actions", "euros", "maintenant",
        # "L'entreprise est-elle bien valorisée ?" counted only "est" and the
        # grounding note came out in English (2026-11-13).
        "elle", "elles", "ils", "du", "cette", "comment", "combien", "pourquoi",
        "entreprise", "l'entreprise", "l’entreprise", "société", "valorisée", "valorisé",
    }
)

_WORD_RE = re.compile(r"[a-zàâçéèêëîïôûùüÿœæ'’]+")


def writes_chinese(text: str | None) -> bool:
    """Return whether the text contains CJK ideographs."""
    return bool(re.search(r"[㐀-鿿]", text or ""))


def writes_french(text: str | None) -> bool:
    """Return whether the user's message is French (and not Chinese)."""
    if not text or writes_chinese(text):
        return False
    words = _WORD_RE.findall(text.casefold())
    return sum(word in FRENCH_WORDS for word in words) >= 2
