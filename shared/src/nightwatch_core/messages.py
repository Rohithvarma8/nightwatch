"""Deterministic notification text (push + email). Never LLM text: built from incident fields."""

import re
from datetime import datetime
from typing import Any, Literal

from nightwatch_core.models import Incident
from nightwatch_core.timefmt import spoken_until

SIGNATURE = "—Night Watch"
REPLAY_LABEL = "Replayed alert"
Kind = Literal["notify", "escalation"]


def sentence(text: str) -> str:
    """Exactly one sentence ending: 'Avoid sparks' / 'Avoid sparks..' → 'Avoid sparks.'"""
    text = re.sub(r"[\s.;:,]+$", "", text.strip())
    if not text:
        return ""
    return text if text[-1] in "!?" else f"{text}."


def notification(incident: Incident, tz: str, now: datetime, kind: Kind) -> tuple[str, str]:
    """(title, body). Title, place, until-time, top action, signature; replays are labeled."""
    label = f"{REPLAY_LABEL}: " if incident.replay else ""
    place = incident.area_name if incident.kind == "hazard" else None  # prod: area = service
    what = incident.title + (f" for {place}" if place else "")
    until = spoken_until(incident.ends_at, tz, now) if incident.kind == "hazard" else None
    headline = f"{what} until {until}" if until else what
    parts = [f"{label}{sentence(headline)}"]
    if incident.top_action:
        parts.append(sentence(incident.top_action))
    if kind == "escalation":
        parts.append("Nobody has acknowledged it yet.")
    parts.append(SIGNATURE)
    prefix = "Escalation: " if kind == "escalation" else ""
    title = f"{prefix}{label}{incident.title}"
    return title, " ".join(parts)


def wire_message(
    kind: Kind, household_id: str, incident_id: str, contact_id: str, title: str, body: str
) -> dict[str, Any]:
    """SNS message for the notifier Lambda. No contact details: the notifier looks them up."""
    return {
        "kind": kind,
        "household_id": household_id,
        "incident_id": incident_id,
        "contact_id": contact_id,
        "title": title,
        "body": body,
        "priority": "high" if kind == "escalation" else "default",
    }
