"""Deterministic correlation rules (pure, no I/O). Every grouping decision emits typed Evidence.

Rules:
- Same hazard family + same zone + same replay flag → one incident (NWS update chains).
- Fire risk: a Red Flag Warning / Fire Weather Watch and a wind alert (High Wind Watch/Warning,
  Wind Advisory) for the same zone with overlapping time windows → one "Fire risk" incident,
  the wind alert as a supporting signal (Evidence type `related_hazard`). Red flag criteria are
  wind + low humidity, so this pairing is meteorologically grounded.
- Nothing else merges across hazard families, and nothing links home hazards to prod incidents.
"""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from nightwatch_core.models import (
    SEVERITY_RANK,
    Evidence,
    HazardFamily,
    Household,
    Incident,
    Severity,
    Signal,
    SignalRef,
)
from nightwatch_core.timefmt import parse_utc, to_utc_iso
from nightwatch_pipeline.triage import templates

FIRE_EVENTS = frozenset({"Red Flag Warning", "Fire Weather Watch"})
WIND_EVENTS = frozenset({"High Wind Watch", "High Wind Warning", "Wind Advisory"})
FIRE_RISK_TITLE = "Fire risk"


def correlation_key(signal: Signal) -> str:
    """household + hazard family + area. Replays never merge into live incidents."""
    key = f"{signal.household_id}#{signal.hazard_family}#{signal.area}"
    return f"{key}#replay" if signal.replay else key


def _window(signal: Signal) -> tuple[datetime, datetime]:
    return parse_utc(signal.onset_at or signal.sent_at), parse_utc(signal.ends_at)


def windows_overlap(a: Signal, b: Signal) -> bool:
    a_start, a_end = _window(a)
    b_start, b_end = _window(b)
    return a_start < b_end and b_start < a_end


def is_fire_risk_pair(fire: Signal, wind: Signal) -> bool:
    return (
        fire.event in FIRE_EVENTS
        and wind.event in WIND_EVENTS
        and fire.household_id == wind.household_id
        and fire.area == wind.area
        and fire.replay == wind.replay
        and windows_overlap(fire, wind)
    )


def current_by_family(signals: Iterable[Signal]) -> dict[HazardFamily, Signal]:
    """Newest message per hazard family (NWS updates supersede earlier ones)."""
    current: dict[HazardFamily, Signal] = {}
    for s in sorted(signals, key=lambda s: (s.sent_at, s.external_id)):
        current[s.hazard_family] = s
    return current


def active_by_family(signals: Iterable[Signal], now: datetime) -> dict[HazardFamily, Signal]:
    return {
        family: s
        for family, s in current_by_family(signals).items()
        if s.message_type != "Cancel" and parse_utc(s.ends_at) > now
    }


def _nws_evidence(signal: Signal) -> Evidence:
    return Evidence(
        type="nws_alert",
        detail=f"NWS {signal.event}, {signal.area_name}",
        weight=1.0,
        source_url=signal.url,
    )


def related_hazard_evidence(fire: Signal, wind: Signal) -> Evidence:
    return Evidence(
        type="related_hazard",
        detail=f"{wind.event} in the same zone during the {fire.event} window",
        weight=0.6,
        source_url=wind.url,
    )


@dataclass(frozen=True)
class Derived:
    title: str
    severity: Severity
    status: str  # "open" or "resolved"
    ends_at: str
    primary: Signal
    supporting: Signal | None
    evidence: list[Evidence]
    refs: list[SignalRef]
    content_hash: str


def _primary_family(active: dict[HazardFamily, Signal]) -> HazardFamily:
    if "fire_weather" in active:
        return "fire_weather"
    # Otherwise the most severe active family (ties: newest message).
    return min(active, key=lambda f: (SEVERITY_RANK[active[f].severity], active[f].sent_at))


def derive(signals: list[Signal], now: datetime) -> Derived:
    """Incident state as a pure function of its member signals."""
    current = current_by_family(signals)
    active = active_by_family(signals, now)
    pool = active or current  # nothing active → resolved, described by its last messages
    primary_family = _primary_family(pool)
    primary = pool[primary_family]
    supporting = next(
        (s for f, s in pool.items() if f != primary_family and is_fire_risk_pair(primary, s)),
        None,
    )
    evidence = [_nws_evidence(primary)]
    if supporting is not None:
        evidence += [related_hazard_evidence(primary, supporting), _nws_evidence(supporting)]
    same_family = [s for s in signals if s.hazard_family == primary_family]
    if len(same_family) > 1:
        evidence.append(
            Evidence(
                type="same_hazard_family",
                detail=f"{len(same_family)} NWS messages grouped",
                weight=0.5,
            )
        )
    members = [primary] + ([supporting] if supporting else [])
    severity: Severity = min(members, key=lambda s: SEVERITY_RANK[s.severity]).severity
    refs = [
        SignalRef(
            source=s.source,
            external_id=s.external_id,
            observed_at=s.sent_at,
            summary=s.headline,
            url=s.url,
            event=s.event,
            hazard_family=s.hazard_family,
            message_type=s.message_type,
            certainty=s.nws_certainty,
            ends_at=s.ends_at,
            role="primary" if s.hazard_family == primary_family else "supporting",
        )
        for s in sorted(signals, key=lambda s: (s.sent_at, s.external_id))
    ]
    status = "open" if active else "resolved"
    fingerprint = "|".join([status, *sorted(m.external_id for m in members)])
    return Derived(
        title=FIRE_RISK_TITLE if supporting else primary.event,
        severity=severity,
        status=status,
        ends_at=max(m.ends_at for m in members),
        primary=primary,
        supporting=supporting,
        evidence=evidence,
        refs=refs,
        content_hash=hashlib.sha256(fingerprint.encode()).hexdigest()[:16],
    )


def apply_derived(
    incident: Incident, signals: list[Signal], household: Household, now: datetime
) -> Incident:
    """Recompute an incident from its signals. Keeps an AI summary written for the same content."""
    d = derive(signals, now)
    now_iso = to_utc_iso(now)
    # Acknowledged / escalated are human (or escalation) decisions: only "resolved" overrides them.
    status = (
        d.status
        if d.status == "resolved" or incident.status == "resolved"
        else (incident.status if incident.status in ("acknowledged", "escalated") else "open")
    )
    update: dict = {
        "title": d.title,
        "severity": d.severity,
        "status": status,
        "area_name": d.primary.area_name,
        "ends_at": d.ends_at,
        "evidence": d.evidence,
        "signals": d.refs,
        "content_hash": d.content_hash,
    }
    if status == "resolved" and incident.status != "resolved":
        update["resolved_at"] = now_iso
    if d.content_hash != incident.content_hash:
        # Facts changed: deterministic template now, the triage agent rewrites it async.
        update |= {
            "spoken_summary": templates.spoken_summary(d.primary, d.supporting, household, now),
            "detail_summary": templates.detail_summary(d.primary, d.supporting),
            "recommended_actions": templates.recommended_actions(d.primary, d.supporting),
            "summarizer": templates.summarizer(),
        }
    changed = any(getattr(incident, k) != v for k, v in update.items())
    if changed:
        update["updated_at"] = now_iso
    return incident.model_copy(update=update)


def find_fire_incident_for_wind(
    wind: Signal, active: list[tuple[Incident, list[Signal]]], now: datetime
) -> Incident | None:
    """An open incident whose active fire-weather alert pairs with this wind alert."""
    if wind.event not in WIND_EVENTS:
        return None
    for incident, signals in active:
        fire = active_by_family(signals, now).get("fire_weather")
        if fire is not None and is_fire_risk_pair(fire, wind):
            return incident
    return None


def merge_plan(
    active: list[tuple[Incident, list[Signal]]], now: datetime
) -> list[tuple[Incident, Incident]]:
    """(fire incident, standalone wind incident) pairs to merge. Order-independent: covers a wind
    alert that arrived before its red flag warning, and incidents created before this rule."""
    plan: list[tuple[Incident, Incident]] = []
    taken: set[str] = set()
    fires = [
        (inc, fire)
        for inc, sigs in active
        if (fire := active_by_family(sigs, now).get("fire_weather")) and fire.event in FIRE_EVENTS
    ]
    for inc, sigs in active:
        fams = active_by_family(sigs, now)
        if set(fams) != {"wind"} or inc.id in taken:
            continue
        for fire_inc, fire in fires:
            if fire_inc.id != inc.id and is_fire_risk_pair(fire, fams["wind"]):
                plan.append((fire_inc, inc))
                taken.add(inc.id)
                break
    return plan
