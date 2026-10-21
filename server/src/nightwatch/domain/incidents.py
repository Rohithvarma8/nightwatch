"""Ranking, replay rules, and spoken formatting for active incidents. Pure (no I/O)."""

import re
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol

from nightwatch.domain.dedupe import covers
from nightwatch.domain.models import (
    SEVERITY_RANK,
    ActiveIncidents,
    IncidentView,
    Scope,
    Severity,
)
from nightwatch_core.messages import sentence
from nightwatch_core.models import Contact, DeployRecord, EscalationPolicy, Incident
from nightwatch_core.timefmt import parse_utc

MAX_LIMIT = 5
_SCOPE_KIND = {"home": "hazard", "work": "prod"}
_COUNT_WORDS = ["Nothing", "One thing", "Two things", "Three things", "Four things", "Five things"]
EVIDENCE_PREVIEW = 2
REPLAY_PREFIX = "Replayed alert:"
_DEPLOY_VERSIONS = re.compile(r"\(v(\w+)→v(\w+)\)")  # rules.proximity_evidence detail


class IncidentSource(Protocol):
    """Where tools read incidents from (DynamoDB in prod, fixture in tests and local runs)."""

    def household_name(self) -> str: ...

    def active_incidents(self, now: datetime) -> list[Incident]: ...

    def get_incident(self, incident_id: str) -> Incident | None: ...

    # Household directory (cached per container).
    def household_tz(self) -> str: ...

    def contacts(self) -> list[Contact]: ...

    def escalation_policy(self) -> EscalationPolicy | None: ...

    # Writes (UpdateItem only).
    def acknowledge(self, incident_id: str, now: datetime) -> tuple[Incident | None, bool]:
        """(incident after, whether this call changed it)."""
        ...

    def mark_escalated(self, incident_id: str, now: datetime) -> Incident | None: ...

    def take_notify_slot(self, contact_id: str, now: datetime, limit: int) -> bool: ...

    def add_event(
        self, incident_id: str, event_type: str, now: datetime, **detail: str
    ) -> None: ...

    def latest_deploy(self, service: str) -> DeployRecord | None: ...


class Notifier(Protocol):
    def publish(self, msg: dict) -> str: ...


def is_active(incident: Incident, now: datetime) -> bool:
    """Still open and its alert hasn't ended (the sweep may not have run yet)."""
    return incident.status != "resolved" and parse_utc(incident.ends_at) > now


def rank(incidents: list[Incident]) -> list[Incident]:
    """Most severe first, then most recent first."""
    newest_first = sorted(incidents, key=lambda i: i.started_at, reverse=True)
    return sorted(newest_first, key=lambda i: SEVERITY_RANK[i.severity])


def without_shadowed_replays(incidents: list[Incident]) -> list[Incident]:
    """Drop replays when a live incident of the same hazard family exists.

    Replays only appear when they're the only data for their hazard (and stay labeled).
    """
    live_families = set().union(*(i.hazard_families for i in incidents if not i.replay))
    return [i for i in incidents if not i.replay or not (i.hazard_families & live_families)]


def overview(incidents: list[Incident], now: datetime) -> list[Incident]:
    """The default ranked list Alexa reads: active, live-over-replay, ranked."""
    return rank(without_shadowed_replays([i for i in incidents if is_active(i, now)]))


def candidates(incidents: list[Incident], now: datetime) -> list[Incident]:
    """Everything active, in overview order, then any shadowed replays (for explicit lookups)."""
    shown = overview(incidents, now)
    rest = rank([i for i in incidents if is_active(i, now) and i not in shown])
    return shown + rest


def select_active(
    incidents: list[Incident], scope: Scope, min_severity: Severity, limit: int
) -> list[Incident]:
    """Already-ranked incidents filtered by scope and severity, capped at `limit`."""
    threshold = SEVERITY_RANK[min_severity]
    kept = [
        i
        for i in incidents
        if SEVERITY_RANK[i.severity] <= threshold
        and (scope == "all" or i.kind == _SCOPE_KIND[scope])
    ]
    return kept[: max(1, min(limit, MAX_LIMIT))]


def spoken_title(incident: Incident | IncidentView) -> str:
    return f"{REPLAY_PREFIX} {incident.title}" if incident.replay else incident.title


def inline_title(incident: Incident | IncidentView) -> str:
    """Mid-sentence form: 'the replayed Red Flag Warning' (not 'the Replayed alert: …')."""
    return f"replayed {incident.title}" if incident.replay else incident.title


def deploy_versions(incident: Incident) -> str | None:
    """ "v2→v3" from deploy_proximity evidence, for the card. None for hazards."""
    for e in incident.evidence:
        if e.type == "deploy_proximity" and (m := _DEPLOY_VERSIONS.search(e.detail)):
            return f"v{m[1]}→v{m[2]}"
    return None


def spoken_action(incident: Incident) -> str:
    """The top action to read after the summary, or "" when the summary already says it."""
    action = incident.top_action
    return "" if not action or covers(incident.spoken_summary, action, incident.title) else action


def do_now(incident: Incident, fallbacks: Sequence[str] = ()) -> str:
    """The card's "Do now": the first action (then runbook step) the summary doesn't already say.

    Prod keeps its top action: the rules pin rollback there.
    """
    if incident.kind == "prod" or not incident.top_action:
        return incident.top_action
    for action in [*incident.recommended_actions, *fallbacks]:
        if not covers(incident.spoken_summary, action, incident.title):
            return action
    return ""


def to_view(incident: Incident, fallbacks: Sequence[str] = ()) -> IncidentView:
    return IncidentView(
        id=incident.id,
        kind=incident.kind,
        title=incident.title,
        severity=incident.severity,
        status=incident.status,
        started_at=incident.started_at,
        spoken_summary=incident.spoken_summary,
        top_action=do_now(incident, fallbacks),
        evidence_preview=[e.detail for e in incident.evidence[:EVIDENCE_PREVIEW]],
        deploy_versions=deploy_versions(incident),
        escalation_due_at=incident.escalation_due_at if incident.status == "open" else None,
        replay=incident.replay,
        replay_original_time=incident.replay_original_time,
    )


def spoken_overview(incidents: list[Incident]) -> str:
    """Short text Alexa can speak from. Never includes IDs or a caution the summary already has."""
    if not incidents:
        return "All clear. No active incidents right now."
    lead = _COUNT_WORDS[len(incidents)] if len(incidents) < len(_COUNT_WORDS) else "Several things"
    parts = [f"{lead}."]
    for n, inc in enumerate(incidents, start=1):
        status = f", {inc.status}" if inc.status in ("acknowledged", "escalated") else ""
        line = f"{n}. {spoken_title(inc)}, {inc.severity}{status}: {sentence(inc.spoken_summary)}"
        if action := spoken_action(inc):
            line += f" {sentence(action)}"
        parts.append(line)
    return " ".join(parts)


def build_active_incidents(
    incidents: list[Incident],
    household: str,
    as_of: str,
    fallbacks: Callable[[Incident], Sequence[str]] = lambda _: (),
) -> ActiveIncidents:
    views = [to_view(i, fallbacks(i)) for i in incidents]
    return ActiveIncidents(
        as_of=as_of,
        household=household,
        spoken_overview=spoken_overview(incidents),
        incidents=views,
    )
