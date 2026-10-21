import json
from pathlib import Path

import pytest

from nightwatch_core.models import Incident, Summarizer
from nightwatch_pipeline.demo_reset import check_alert, is_ready, is_reset_target
from nightwatch_pipeline.triage.rules import FIRE_EVENTS, WIND_EVENTS


@pytest.mark.parametrize(
    ("pk", "sk", "expected"),
    [
        ("INC#inc_1", "META", True),
        ("SIG#nws#x", "META", True),
        ("HH#hh_demo", "OPENKEY#hh_demo#fire_weather#CAZ374#replay", True),
        ("RATE#hh_demo#c_priya", "2026-10-20T10", True),
        ("HH#hh_demo", "META", False),
        ("HH#hh_demo", "CONTACT#c_priya", False),
        ("SVC#checkout-service", "DEPLOY#d-1", False),
    ],
)
def test_reset_keeps_the_household_and_deploys(pk: str, sk: str, expected: bool) -> None:
    assert is_reset_target({"PK": pk, "SK": sk}) is expected


def _alert(tmp_path: Path, event: str, ugc: list[str]) -> Path:
    path = tmp_path / f"{event}.json"
    path.write_text(json.dumps({"properties": {"event": event, "geocode": {"UGC": ugc}}}))
    return path


def test_check_alert_needs_the_event_and_the_demo_zone(tmp_path: Path) -> None:
    assert check_alert(_alert(tmp_path, "Red Flag Warning", ["CAZ374"]), FIRE_EVENTS)
    with pytest.raises(SystemExit):
        check_alert(_alert(tmp_path, "Wind Advisory", ["CAZ374"]), FIRE_EVENTS)
    with pytest.raises(SystemExit):
        check_alert(_alert(tmp_path, "Wind Advisory", ["CAZ375"]), WIND_EVENTS)


def _incident(**update: object) -> Incident:
    base = Incident(
        id="inc_1",
        household_id="hh_demo",
        kind="hazard",
        title="Fire risk",
        severity="high",
        status="open",
        started_at="2026-10-20T10:00:00Z",
        updated_at="2026-10-20T10:00:00Z",
        ends_at="2099-01-01T00:00:00Z",
        correlation_key="k",
        content_hash="h2",
        spoken_summary="s",
        detail_summary="d",
        escalation_due_at="2026-10-20T10:02:00Z",
        summarizer=Summarizer(model="m", latency_ms=1, fallback_used=False, content_hash="h2"),
    )
    return base.model_copy(update=update)


def test_ready_only_when_merged_triaged_and_timed() -> None:
    assert is_ready(_incident())
    assert not is_ready(_incident(title="Red Flag Warning"))
    assert not is_ready(_incident(escalation_due_at=None))
    assert not is_ready(_incident(status="acknowledged"))
    stale = Summarizer(model="m", latency_ms=1, fallback_used=False, content_hash="h1")
    assert not is_ready(_incident(summarizer=stale))
