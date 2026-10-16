"""Filtering, ranking, and spoken formatting for active incidents."""

from datetime import datetime
from typing import Protocol

from nightwatch.domain.models import (
    SEVERITY_RANK,
    ActiveIncidents,
    IncidentView,
    Scope,
    Severity,
)
from nightwatch_core.models import Incident
from nightwatch_core.timefmt import parse_utc

MAX_LIMIT = 5
_SCOPE_KIND = {"home": "hazard", "work": "prod"}
_COUNT_WORDS = ["Nothing", "One thing", "Two things", "Three things", "Four things", "Five things"]
EVIDENCE_PREVIEW = 2


class IncidentSource(Protocol):
    """Where the tool reads active incidents from (DynamoDB in prod, fixture in tests)."""

    def household_name(self) -> str: ...

    def active_incidents(self, now: datetime) -> list[IncidentView]: ...


def is_active(incident: Incident, now: datetime) -> bool:
    """Still open and its alert hasn't ended (the sweep may not have run yet)."""
    return incident.status != "resolved" and parse_utc(incident.ends_at) > now


def to_view(incident: Incident) -> IncidentView:
    return IncidentView(
        id=incident.id,
        kind=incident.kind,
        title=incident.title,
        severity=incident.severity,
        status=incident.status,
        started_at=incident.started_at,
        spoken_summary=incident.spoken_summary,
        top_action=incident.top_action,
        evidence_preview=[e.detail for e in incident.evidence[:EVIDENCE_PREVIEW]],
        escalation_due_at=None,
        replay=incident.replay,
        replay_original_time=incident.replay_original_time,
    )


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
