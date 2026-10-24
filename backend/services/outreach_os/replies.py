"""Reply classification for inbound answers (simulated in this slice, webhook-driven later)."""

from __future__ import annotations

import re
import unicodedata

_OPT_OUT_EXACT = {"stop", "unsubscribe", "desinscription", "desabonnement", "arret", "cancel"}
_STOP_FILLER = {"svp", "please", "merci", "thanks", "now", "s'il", "vous", "plait", "all", "tout"}
_OPT_OUT_PHRASES = (
    "unsubscribe",
    "desinscri",  # désinscrire, désinscription, désinscrivez
    "desabonn",
    "ne plus recevoir",
    "ne souhaite plus",
    "retirez moi",
    "supprimez moi",
    "remove me",
    "stop emailing",
    "stop sending",
    "do not contact",
    "ne me contactez plus",
    "arretez de m",
)


def _fold(text: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", stripped.lower())).strip()


def is_opt_out(text: str) -> bool:
    """True when a reply asks to stop receiving messages. A lone keyword or an explicit phrase counts;
    a keyword inside another word or sentence ('non-stop', 'please do not stop by') does not."""
    folded = _fold(text)
    if not folded:
        return False
    words = folded.split(" ")
    if folded in _OPT_OUT_EXACT or (words[0] == "stop" and all(w in _STOP_FILLER for w in words[1:])):
        return True
    return any(phrase in folded for phrase in _OPT_OUT_PHRASES)
