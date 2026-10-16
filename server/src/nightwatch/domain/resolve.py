"""Find the incident the user means: by id, by a fuzzy reference, or the top-ranked one.

Deterministic keyword matching on title, alert events, and hazard family ("the fire one",
"the wind thing", "the checkout alarm"). No LLM.
"""

import re

from nightwatch.domain.incidents import spoken_title
from nightwatch_core.models import Incident

_FAMILY_WORDS: dict[str, set[str]] = {
    "fire_weather": {"fire", "fires", "red", "flag", "wildfire", "burn", "spark"},
    "wind": {"wind", "winds", "windy", "gust", "gusts", "gusty"},
    "heat": {"heat", "hot", "heatwave"},
    "cold": {"cold", "freeze", "freezing", "frost"},
    "coastal": {"beach", "surf", "coast", "coastal", "flood", "tide"},
    "air": {"air", "aqi", "smoke", "smoky", "quality", "pollution"},
    "prod": {
        "prod", "production", "deploy", "deployment", "checkout", "latency", "service",
        "server", "alarm", "outage", "work", "site", "app", "release", "rollback",
    },
}  # fmt: skip
_STOPWORDS = {
    "the", "a", "an", "one", "thing", "that", "this", "it", "about", "alert", "warning",
    "incident", "issue", "problem", "what", "whats", "is", "with", "on", "for", "of", "my",
}  # fmt: skip


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS}


def keywords(incident: Incident) -> set[str]:
    words = _tokens(incident.title)
    for ref in incident.signals:
        if ref.event:
            words |= _tokens(ref.event)
    for family in incident.hazard_families:
        words |= _FAMILY_WORDS.get(family, set()) | {family}
    return words


def match_reference(incidents: list[Incident], reference: str) -> Incident | None:
    """Best keyword overlap; ties go to the earlier (higher-ranked) incident."""
    wanted = _tokens(reference)
    if not wanted:
        return incidents[0] if incidents else None
    best, best_score = None, 0
    for incident in incidents:
        score = len(wanted & keywords(incident))
        if score > best_score:
            best, best_score = incident, score
    return best


def not_found_message(reference: str | None, active: list[Incident]) -> str:
    what = f"matching '{reference}'" if reference else "with that ID"
    if not active:
        return f"I couldn't find an incident {what}. Nothing is active right now."
    names = "; ".join(spoken_title(i) for i in active)
    return f"I couldn't find an incident {what}. Active right now: {names}."
