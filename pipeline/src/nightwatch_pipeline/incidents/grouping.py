"""Pure grouping logic: signal + open incident → new incident state. No I/O."""

from datetime import datetime

from nightwatch_core.ids import new_id
from nightwatch_core.models import Evidence, Household, Incident, Signal, SignalRef, Summarizer
from nightwatch_core.timefmt import parse_utc, to_utc_iso
from nightwatch_pipeline.triage import templates


def correlation_key(signal: Signal) -> str:
    """household + hazard family + area. Replays never merge into live incidents."""
    key = f"{signal.household_id}#{signal.hazard_family}#{signal.area}"
    return f"{key}#replay" if signal.replay else key


def _ref(signal: Signal) -> SignalRef:
    return SignalRef(
        source=signal.source,
        external_id=signal.external_id,
        observed_at=signal.sent_at,  # when the source issued it
        summary=signal.headline,
        url=signal.url,
    )


def _evidence(signal: Signal, refs: list[SignalRef]) -> list[Evidence]:
    evidence = [
        Evidence(
            type="nws_alert",
            detail=f"NWS {signal.event}, {signal.area_name}",
            weight=1.0,
            source_url=signal.url,
        )
    ]
    if len(refs) > 1:
        evidence.append(
            Evidence(
                type="same_hazard_family",
                detail=f"{len(refs)} NWS messages grouped",
                weight=0.5,
            )
        )
    return evidence


def apply_signal(
    existing: Incident | None, signal: Signal, household: Household, now: datetime
) -> Incident | None:
    """Fold a signal into its open incident (or start one). None = nothing to write."""
    now_iso = to_utc_iso(now)
    if existing is None:
        if signal.message_type == "Cancel" or parse_utc(signal.ends_at) <= now:
            return None
        refs = [_ref(signal)]
        return Incident(
            id=new_id("inc"),
            household_id=signal.household_id,
            kind="hazard",
            title=signal.event,
            severity=signal.severity,
            status="open",
            started_at=signal.onset_at or signal.sent_at,
            updated_at=now_iso,
            ends_at=signal.ends_at,
            correlation_key=correlation_key(signal),
            signals=refs,
            evidence=_evidence(signal, refs),
            spoken_summary=templates.spoken_summary(signal, household, now),
            detail_summary=templates.detail_summary(signal),
            recommended_actions=templates.recommended_actions(signal),
            replay=signal.replay,
            replay_original_time=signal.replay_original_time,
            summarizer=Summarizer(
                model=templates.TEMPLATE_MODEL, latency_ms=0, fallback_used=False
            ),
        )

    if any(r.external_id == signal.external_id for r in existing.signals):
        return None  # redelivered event
    refs = [*existing.signals, _ref(signal)]
    newest = max(r.observed_at for r in existing.signals)
    if signal.sent_at < newest:
        # Older message arrived late: keep it on record, don't let it override state.
        return existing.model_copy(update={"signals": refs, "updated_at": now_iso})
    if signal.message_type == "Cancel":
        return existing.model_copy(
            update={
                "signals": refs,
                "status": "resolved",
                "resolved_at": now_iso,
                "updated_at": now_iso,
                "ends_at": now_iso,
            }
        )
    return existing.model_copy(
        update={
            "title": signal.event,
            "severity": signal.severity,
            "updated_at": now_iso,
            "ends_at": signal.ends_at,
            "signals": refs,
            "evidence": _evidence(signal, refs),
            "spoken_summary": templates.spoken_summary(signal, household, now),
            "detail_summary": templates.detail_summary(signal),
            "recommended_actions": templates.recommended_actions(signal),
        }
    )


def expire(incident: Incident, now: datetime) -> Incident | None:
    """Resolve an incident whose alert has ended. None if still active."""
    if parse_utc(incident.ends_at) > now:
        return None
    now_iso = to_utc_iso(now)
    return incident.model_copy(
        update={"status": "resolved", "resolved_at": now_iso, "updated_at": now_iso}
    )
