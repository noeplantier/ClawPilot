"""Credits: a daily allowance of AI work, and the outreach models it pays for. Pure: no I/O, `now` injected.

Nothing here costs money by itself: the credits cap what the server asks an AI provider (a free tier has limits, a
paid one bills per call). Two windows, like a usage meter: a *session* of 5 hours that starts with the first spend,
and the *day* (Europe/Paris). A spend is refused, before any provider call, when either window would go over its
limit; the refusal says which one and when it resets. The model "Gabarit" never calls an AI and costs nothing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence
from zoneinfo import ZoneInfo

SESSION_HOURS = 5
PARIS = ZoneInfo("Europe/Paris")
DEFAULT_PER_DAY = 100
DEFAULT_PER_SESSION = 30
MAX_LIMIT = 100_000


@dataclass(frozen=True)
class OutreachModel:
    id: str
    name: str
    tagline: str  # one line, shown under the name
    description: str
    credits: int  # per message written
    uses_ai: bool
    max_words: Optional[int]  # the length the message is asked to stay under
    max_tokens: Optional[int]
    temperature: Optional[float]
    instruction: Optional[str]  # appended to the writing instructions (never replaces the safety rules)


MODELS: tuple[OutreachModel, ...] = (
    OutreachModel(
        id="gabarit",
        name="Plantiers Gabarit",
        tagline="Votre modèle approuvé, sans IA",
        description="Le message de votre campagne, rendu avec les faits détectés. Aucun appel à un fournisseur d'IA.",
        credits=0,
        uses_ai=False,
        max_words=None,
        max_tokens=None,
        temperature=None,
        instruction=None,
    ),
    OutreachModel(
        id="rapide",
        name="Plantiers Rapide",
        tagline="Court et direct, pour les gros volumes",
        description="Trois à quatre phrases, une seule idée, un appel à l'action simple.",
        credits=1,
        uses_ai=True,
        max_words=90,
        max_tokens=350,
        temperature=0.4,
        instruction="Écris un message très court : 90 mots au plus, une seule idée, un seul appel à l'action.",
    ),
    OutreachModel(
        id="equilibre",
        name="Plantiers Équilibre",
        tagline="Le bon compromis, recommandé",
        description="Un message personnalisé à partir des faits détectés, de longueur moyenne.",
        credits=2,
        uses_ai=True,
        max_words=140,
        max_tokens=600,
        temperature=0.6,
        instruction="Écris un message de 140 mots au plus, personnalisé avec les faits fournis.",
    ),
    OutreachModel(
        id="precision",
        name="Plantiers Précision",
        tagline="Le plus soigné, pour les prospects prioritaires",
        description="Chaque fait détecté relié à votre offre, un ton travaillé. Coûte plus de crédits.",
        credits=4,
        uses_ai=True,
        max_words=180,
        max_tokens=900,
        temperature=0.7,
        instruction=(
            "Écris un message soigné de 180 mots au plus : relie chaque fait fourni à un bénéfice précis de l'offre, "
            "sans rien affirmer d'autre."
        ),
    ),
)
DEFAULT_MODEL = "equilibre"
_BY_ID = {m.id: m for m in MODELS}


def model(model_id: Optional[str]) -> OutreachModel:
    """The model of this id; an unknown or empty id is the default one (never an error at writing time)."""
    return _BY_ID.get(model_id or "", _BY_ID[DEFAULT_MODEL])


def is_model(model_id: str) -> bool:
    return model_id in _BY_ID


@dataclass(frozen=True)
class Limits:
    per_day: int
    per_session: int


def limits_from(env: dict[str, str]) -> Limits:
    """CREDITS_PER_DAY / CREDITS_PER_SESSION; a missing, unreadable or negative value is the default."""

    def read(name: str, default: int) -> int:
        try:
            value = int(str(env.get(name, "")).strip())
        except ValueError:
            return default
        return value if 0 <= value <= MAX_LIMIT else default

    return Limits(
        per_day=read("CREDITS_PER_DAY", DEFAULT_PER_DAY), per_session=read("CREDITS_PER_SESSION", DEFAULT_PER_SESSION)
    )


@dataclass(frozen=True)
class Window:
    key: str  # "session" | "day"
    label: str
    limit: int
    used: int
    remaining: int
    resets_at: Optional[datetime]  # None: nothing spent in this window yet

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _aware(at: datetime) -> datetime:
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def day_start(now: datetime) -> datetime:
    local = _aware(now).astimezone(PARIS)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def windows(spends: Iterable[tuple[datetime, int]], now: datetime, limits: Limits) -> list[Window]:
    """The session and the day, from the spends (when, credits). A session starts with the first spend after the
    previous one ended and lasts SESSION_HOURS; once it is over, nothing counts until the next spend starts one."""
    now = _aware(now)
    events = sorted((_aware(at), int(n)) for at, n in spends if n > 0)
    length = timedelta(hours=SESSION_HOURS)
    start: Optional[datetime] = None
    for at, _ in events:
        if at > now:
            continue
        if start is None or at >= start + length:
            start = at
    session_used = 0
    session_reset: Optional[datetime] = None
    if start is not None and now < start + length:
        session_used = sum(n for at, n in events if start <= at <= now)
        session_reset = start + length
    today = day_start(now)
    day_used = sum(n for at, n in events if today <= at <= now)
    tomorrow = (today.astimezone(PARIS) + timedelta(days=1)).replace(hour=0).astimezone(timezone.utc)
    return [
        Window(
            key="session",
            label=f"Session ({SESSION_HOURS} h)",
            limit=limits.per_session,
            used=session_used,
            remaining=max(0, limits.per_session - session_used),
            resets_at=session_reset,
        ),
        Window(
            key="day",
            label="Aujourd'hui",
            limit=limits.per_day,
            used=day_used,
            remaining=max(0, limits.per_day - day_used),
            resets_at=tomorrow if day_used else None,
        ),
    ]


@dataclass(frozen=True)
class Refusal:
    code: str  # "credits_exhausted"
    window: str
    message: str
    resets_at: Optional[datetime]


def check(current: Sequence[Window], cost: int, now: datetime) -> Optional[Refusal]:
    """None when `cost` credits fit in every window; else why not, and when it resets. A cost of 0 always fits."""
    if cost <= 0:
        return None
    for w in current:
        if w.used + cost > w.limit:
            resets = w.resets_at
            if resets is None:  # an empty window that is still too small: it is the limit itself
                when = "augmentez la limite (CREDITS_PER_DAY / CREDITS_PER_SESSION)"
            else:
                when = f"réinitialisation à {resets.astimezone(PARIS).strftime('%H:%M')} (heure de Paris)"
            return Refusal(
                code="credits_exhausted",
                window=w.key,
                message=(
                    f"Crédits épuisés pour {w.label.lower()} : {w.used}/{w.limit} utilisés, il en faut {cost} ; {when}."
                ),
                resets_at=resets,
            )
    return None


def with_instruction(messages: Sequence[dict[str, str]], chosen: OutreachModel) -> list[dict[str, str]]:
    """The writing instructions with the model's length and style added to the first system message (the safety rules of
    that message are kept as they are; nothing is removed)."""
    out = [dict(m) for m in messages]
    if not chosen.instruction:
        return out
    for m in out:
        if m.get("role") == "system":
            m["content"] = f"{m.get('content', '')}\n\n{chosen.instruction}".strip()
            return out
    return [{"role": "system", "content": chosen.instruction}, *out]
