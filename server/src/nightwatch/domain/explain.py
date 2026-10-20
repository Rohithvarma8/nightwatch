"""explain_incident output: what happened, what it means, evidence, confidence, timeline."""

from typing import Literal

from pydantic import BaseModel

from nightwatch.domain.incidents import sentence, spoken_title
from nightwatch_core.models import Incident

Depth = Literal["brief", "full"]
Confidence = Literal["high", "medium", "low"]

_SOURCE_NAMES = {
    "nws": "National Weather Service",
    "airnow": "AirNow",
    "fire": "NIFC",
    "cloudwatch": "CloudWatch",
    "codedeploy": "CodeDeploy",
}
_MEANING: dict[str, str] = {
    "fire_risk": "Dry air and strong wind together make it easy for a fire to start and spread.",
    "fire_weather": "Conditions make it easy for a fire to start and spread.",
    "wind": "Strong gusts can knock down branches and power lines and toss loose items.",
    "heat": "Heat can make people and pets sick, especially without air conditioning.",
    "cold": "Freezing temperatures can hurt plants, pets, and exposed pipes.",
    "coastal": "Beach and shoreline conditions are dangerous.",
    "air": "The air outside can irritate lungs, especially for sensitive people.",
    "prod": "Customers may be seeing slow or failed requests.",
    "other": "The National Weather Service has issued an alert for your area.",
}
_VERB = {"Alert": "issued", "Update": "updated", "Cancel": "cancelled"}
BRIEF_EVIDENCE = 2
BRIEF_TIMELINE = 3


class EvidenceItem(BaseModel):
    type: str
    detail: str
    weight: float
    source_url: str | None


class TimelineEntry(BaseModel):
    at: str
    event: str


class Explanation(BaseModel):
    id: str
    title: str
    what_happened: str
    what_it_means_for_you: str
    evidence: list[EvidenceItem]
    confidence: Confidence
    timeline: list[TimelineEntry]
    sources: list[str]
    replay: bool
    replay_original_time: str | None


def _meaning_key(incident: Incident) -> str:
    if incident.title == "Fire risk":
        return "fire_risk"
    primary = [r for r in incident.signals if r.role == "primary" and r.hazard_family]
    if primary:
        return primary[-1].hazard_family or "other"
    return "prod" if incident.kind == "prod" else "other"


def confidence(incident: Incident) -> Confidence:
    """From the newest primary source message's certainty (NWS CAP)."""
    primary = [r for r in incident.signals if r.role == "primary" and r.certainty]
    certainty = primary[-1].certainty if primary else None
    if certainty in {"Observed", "Likely"}:
        return "high"
    if certainty == "Possible" or certainty is None:
        return "medium"
    return "low"


def timeline(incident: Incident) -> list[TimelineEntry]:
    entries = [
        TimelineEntry(
            at=r.observed_at,
            event=f"{_SOURCE_NAMES.get(r.source, r.source)} "
            f"{_VERB.get(r.message_type or '', 'reported')} {r.event or r.summary}",
        )
        for r in incident.signals
    ]
    if incident.resolved_at:
        entries.append(TimelineEntry(at=incident.resolved_at, event="Incident resolved"))
    return sorted(entries, key=lambda e: e.at)


def explain(incident: Incident, depth: Depth) -> Explanation:
    evidence = [EvidenceItem(**e.model_dump()) for e in incident.evidence]
    events = timeline(incident)
    if depth == "brief":
        evidence, events = evidence[:BRIEF_EVIDENCE], events[-BRIEF_TIMELINE:]
    meaning = _MEANING[_meaning_key(incident)]
    if incident.top_action:
        meaning = f"{meaning} {sentence(incident.top_action)}"
    return Explanation(
        id=incident.id,
        title=incident.title,
        what_happened=incident.detail_summary or incident.spoken_summary,
        what_it_means_for_you=meaning,
        evidence=evidence,
        confidence=confidence(incident),
        timeline=events,
        sources=sorted({_SOURCE_NAMES.get(r.source, r.source) for r in incident.signals}),
        replay=incident.replay,
        replay_original_time=incident.replay_original_time,
    )


def spoken_explanation(incident: Incident, exp: Explanation) -> str:
    """Spoken answer to "why?": the summary, what it means, and the evidence. No IDs."""
    spoken = {e.detail: e.spoken for e in incident.evidence if e.spoken}  # ID-free variants
    because = "; ".join(spoken.get(e.detail, e.detail) for e in exp.evidence[:BRIEF_EVIDENCE])
    parts = [
        f"{spoken_title(incident)}. {sentence(incident.spoken_summary)}",
        exp.what_it_means_for_you,
    ]
    if because:
        parts.append(f"Based on: {because}.")
    parts.append(f"Confidence is {exp.confidence}.")
    return " ".join(parts)
