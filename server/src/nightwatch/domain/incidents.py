"""Filtering, ranking, and spoken formatting for active incidents."""

from nightwatch.domain.models import (
    SEVERITY_RANK,
    ActiveIncidents,
    IncidentView,
    Scope,
    Severity,
)

MAX_LIMIT = 5
_SCOPE_KIND = {"home": "hazard", "work": "prod"}
_COUNT_WORDS = ["Nothing", "One thing", "Two things", "Three things", "Four things", "Five things"]


def select_active(
    incidents: list[IncidentView], scope: Scope, min_severity: Severity, limit: int
) -> list[IncidentView]:
    """Open-ish incidents in scope at or above min_severity, most severe first."""
    threshold = SEVERITY_RANK[min_severity]
    kept = [
        i
        for i in incidents
        if i.status != "resolved"
        and SEVERITY_RANK[i.severity] <= threshold
        and (scope == "all" or i.kind == _SCOPE_KIND[scope])
    ]
    kept.sort(key=lambda i: (SEVERITY_RANK[i.severity], i.started_at))
    return kept[: max(1, min(limit, MAX_LIMIT))]


def spoken_overview(incidents: list[IncidentView]) -> str:
    """Short text Alexa can speak from. Never includes IDs."""
    if not incidents:
        return "All clear. No active incidents right now."
    lead = _COUNT_WORDS[len(incidents)] if len(incidents) < len(_COUNT_WORDS) else "Several things"
    parts = [f"{lead}."]
    for n, inc in enumerate(incidents, start=1):
        parts.append(f"{n}. {inc.title}, {inc.severity}: {inc.spoken_summary} {inc.top_action}.")
    return " ".join(parts)


def build_active_incidents(
    incidents: list[IncidentView], household: str, as_of: str
) -> ActiveIncidents:
    return ActiveIncidents(
        as_of=as_of,
        household=household,
        spoken_overview=spoken_overview(incidents),
        incidents=incidents,
    )
