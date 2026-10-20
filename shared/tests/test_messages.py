from datetime import UTC, datetime
from typing import Any

from nightwatch_core.messages import notification, sentence
from nightwatch_core.models import Incident, Summarizer

NOW = datetime(2026, 10, 19, 20, 0, tzinfo=UTC)  # Monday 1 PM PDT


def _incident(**kw) -> Incident:
    base: dict[str, Any] = dict(
        id="inc_1", household_id="hh_demo", kind="hazard", title="Red Flag Warning",
        severity="high", status="open", started_at="2026-10-19T19:00:00Z",
        updated_at="2026-10-19T19:00:00Z", ends_at="2026-10-21T03:00:00Z",
        correlation_key="k", spoken_summary="s", detail_summary="d",
        recommended_actions=["Avoid anything that could spark a fire"],
        area_name="Southeastern Ventura County Valleys",
        summarizer=Summarizer(model="template-v1", latency_ms=0, fallback_used=False),
    )  # fmt: skip
    return Incident.model_validate(base | kw)


def test_notify_message() -> None:
    title, body = notification(_incident(), "America/Los_Angeles", NOW, "notify")
    assert title == "Red Flag Warning"
    assert body == (
        "Red Flag Warning for Southeastern Ventura County Valleys until 8 PM Tuesday. "
        "Avoid anything that could spark a fire. —Night Watch"
    )


def test_escalation_message_and_replay_label() -> None:
    title, body = notification(_incident(replay=True), "America/Los_Angeles", NOW, "escalation")
    assert title == "Escalation: Replayed alert: Red Flag Warning"
    assert body.startswith("Replayed alert: Red Flag Warning for Southeastern")
    assert "Nobody has acknowledged it yet." in body and body.endswith("—Night Watch")


def test_ai_action_period_is_not_doubled() -> None:
    inc = _incident(recommended_actions=["Avoid activities that can spark fires."])
    _, body = notification(inc, "America/Los_Angeles", NOW, "notify")
    assert ".." not in body


def test_prod_incident_has_no_place_or_until() -> None:
    inc = _incident(kind="prod", title="checkout-service latency", area_name=None,
                    recommended_actions=["Roll back the latest deploy"])  # fmt: skip
    _, body = notification(inc, "America/Los_Angeles", NOW, "notify")
    assert body == "checkout-service latency. Roll back the latest deploy. —Night Watch"


def test_sentence() -> None:
    assert sentence("Go.. ") == "Go." and sentence("Leave now!") == "Leave now!"
