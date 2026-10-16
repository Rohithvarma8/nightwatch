"""Small Incident builder for domain tests."""

from nightwatch_core.models import Evidence, Incident, SignalRef, Summarizer

FAMILY = {
    "Red Flag Warning": "fire_weather",
    "Fire risk": "fire_weather",
    "Wind Advisory": "wind",
    "Heat Advisory": "heat",
}


def incident(
    iid: str,
    title: str,
    severity: str = "high",
    *,
    started_at: str = "2026-10-16T10:00:00Z",
    ends_at: str = "2099-01-01T00:00:00Z",
    replay: bool = False,
    kind: str = "hazard",
    supporting: str | None = None,
    certainty: str = "Likely",
) -> Incident:
    refs = []
    if kind == "hazard":
        event = "Red Flag Warning" if title == "Fire risk" else title
        refs.append(
            SignalRef(
                source="nws", external_id=f"{iid}.1", observed_at=started_at, summary=event,
                url="https://api.weather.gov/x", event=event,
                hazard_family=FAMILY.get(title, "other"),  # type: ignore[arg-type]
                message_type="Alert", certainty=certainty,
            )
        )  # fmt: skip
    if supporting:
        refs.append(
            SignalRef(
                source="nws", external_id=f"{iid}.2", observed_at=started_at, summary=supporting,
                url="https://api.weather.gov/y", event=supporting,
                hazard_family=FAMILY[supporting], message_type="Alert",  # type: ignore[arg-type]
                role="supporting",
            )
        )  # fmt: skip
    return Incident(
        id=iid,
        household_id="hh_demo",
        kind=kind,  # type: ignore[arg-type]
        title=title,
        severity=severity,  # type: ignore[arg-type]
        status="open",
        started_at=started_at,
        updated_at=started_at,
        ends_at=ends_at,
        correlation_key=f"hh_demo#{title}",
        signals=refs,
        evidence=[Evidence(type="nws_alert", detail=f"NWS {title}", weight=1.0)],
        spoken_summary=f"Summary of {title}.",
        detail_summary=f"Details of {title}.",
        recommended_actions=[f"Act on {title}"],
        replay=replay,
        replay_original_time="2026-10-15T20:16:00Z" if replay else None,
        summarizer=Summarizer(model="template-v1", latency_ms=0, fallback_used=False),
    )
