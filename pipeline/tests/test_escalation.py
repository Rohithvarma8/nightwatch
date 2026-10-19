"""Escalation timer (Scheduler), escalation Lambda, notifier, and human-status preservation."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import boto3
import pytest

from nightwatch_core.timefmt import to_utc_iso
from nightwatch_pipeline.escalation.handler import escalate
from nightwatch_pipeline.escalation.schedule import EscalationScheduler, schedule_name
from nightwatch_pipeline.incidents.handler import process_signal
from nightwatch_pipeline.ingest.nws import normalize
from nightwatch_pipeline.notify import handler as notifier
from nightwatch_pipeline.replay import replay
from nightwatch_pipeline.seed import DEMO_HOUSEHOLD, DEMO_POLICY, demo_contact

from .conftest import FIXTURES, NOW, RecordingBus, load

TARGET = "arn:aws:lambda:us-west-2:123456789012:function:nightwatch-escalation"
ROLE = "arn:aws:iam::123456789012:role/nightwatch-escalation-scheduler"


class FakePublisher:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def publish(self, msg: dict[str, Any]) -> str:
        self.sent.append(msg)
        return "msg-1"


@pytest.fixture
def seeded(store):
    store.put_contact(demo_contact("priya@example.com"))
    store.put_policy(DEMO_POLICY)
    return store


@pytest.fixture
def scheduler(aws) -> EscalationScheduler:
    return EscalationScheduler(TARGET, ROLE)


def _replayed_rfw(store, bus):
    replay(Path(FIXTURES / "red_flag_warning_update.json"), store, bus, "hh_demo", NOW)
    return bus.published[-1]


def test_high_severity_incident_gets_one_time_schedule(seeded, bus: RecordingBus, scheduler):
    process_signal(seeded, _replayed_rfw(seeded, bus), NOW, scheduler)
    (inc,) = seeded.list_active("hh_demo")
    due = NOW + timedelta(seconds=DEMO_HOUSEHOLD.ack_timeout_s)  # replay starts "now"
    assert inc.escalation_due_at == to_utc_iso(due)
    assert inc.escalation_schedule_name == schedule_name(inc.id)
    sched = boto3.client("scheduler").get_schedule(Name=schedule_name(inc.id))
    assert sched["ScheduleExpression"] == f"at({due.strftime('%Y-%m-%dT%H:%M:%S')})"
    assert sched["ActionAfterCompletion"] == "DELETE"
    assert sched["Target"]["Arn"] == TARGET
    assert json.loads(sched["Target"]["Input"]) == {
        "incident_id": inc.id,
        "household_id": "hh_demo",
    }


def test_live_alert_clock_starts_no_earlier_than_now(seeded, scheduler):
    s = normalize(load("red_flag_warning_update"), DEMO_HOUSEHOLD, NOW)  # onset 50 min before NOW
    assert s is not None
    seeded.claim_signal(s, NOW)
    process_signal(seeded, s, NOW, scheduler)
    (inc,) = seeded.list_active("hh_demo")
    assert inc.escalation_due_at == to_utc_iso(NOW + timedelta(seconds=120))


def test_moderate_incident_gets_no_schedule(seeded, scheduler):
    s = normalize(load("wind_advisory_update"), DEMO_HOUSEHOLD, NOW)
    assert s is not None
    seeded.claim_signal(s, NOW)
    process_signal(seeded, s, NOW, scheduler)
    (inc,) = seeded.list_active("hh_demo")
    assert inc.severity == "moderate" and inc.escalation_schedule_name is None
    assert boto3.client("scheduler").list_schedules()["Schedules"] == []


def _incident(store, bus, scheduler):
    process_signal(store, _replayed_rfw(store, bus), NOW, scheduler)
    (inc,) = store.list_active("hh_demo")
    return inc


def test_escalates_when_not_acknowledged(seeded, bus, scheduler):
    inc = _incident(seeded, bus, scheduler)
    pub = FakePublisher()
    later = NOW + timedelta(minutes=2)
    assert escalate(seeded, pub, inc.id, later) == "escalated"
    saved = seeded.get_incident(inc.id)
    assert saved.status == "escalated" and saved.escalated_at == to_utc_iso(later)
    (msg,) = pub.sent
    assert msg["kind"] == "escalation" and msg["contact_id"] == "c_priya"
    assert msg["priority"] == "high"
    assert msg["title"] == "Escalation: Replayed alert: Red Flag Warning"
    assert msg["body"].startswith("Replayed alert: Red Flag Warning for Southeastern Ventura")
    assert msg["body"].endswith("Nobody has acknowledged it yet. —Night Watch")
    assert "priya@example.com" not in json.dumps(msg)  # no contact details on the wire
    events = seeded.table.query(
        KeyConditionExpression="PK = :p AND begins_with(SK, :e)",
        ExpressionAttributeValues={":p": f"INC#{inc.id}", ":e": "EVT#"},
    )["Items"]
    assert "escalated" in {e["type"] for e in events}
    # Firing again (Scheduler retry) does nothing.
    assert escalate(seeded, pub, inc.id, later).startswith("noop") and len(pub.sent) == 1


@pytest.mark.parametrize("status", ["acknowledged", "resolved"])
def test_timer_is_a_noop_when_acked_or_resolved(seeded, bus, scheduler, status):
    inc = _incident(seeded, bus, scheduler)
    seeded.table.update_item(
        Key={"PK": f"INC#{inc.id}", "SK": "META"},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status},
    )
    pub = FakePublisher()
    assert escalate(seeded, pub, inc.id, NOW + timedelta(minutes=2)) == f"noop: {status}"
    assert pub.sent == [] and seeded.get_incident(inc.id).status == status


def test_new_signal_keeps_acknowledged_status(seeded, bus, scheduler):
    inc = _incident(seeded, bus, scheduler)
    seeded.table.update_item(
        Key={"PK": f"INC#{inc.id}", "SK": "META"},
        UpdateExpression="SET #s = :s, #v = #v + :one",
        ExpressionAttributeNames={"#s": "status", "#v": "version"},
        ExpressionAttributeValues={":s": "acknowledged", ":one": 1},
    )
    wind = normalize(
        load("wind_advisory_update"),
        DEMO_HOUSEHOLD,
        NOW,
        replay=True,
        external_id="replay:wind",
        replay_original_time="2026-10-15T14:38:00Z",
    )
    assert wind is not None
    seeded.claim_signal(wind, NOW)
    process_signal(seeded, wind, NOW, scheduler)
    saved = seeded.get_incident(inc.id)
    assert saved.title == "Fire risk" and saved.status == "acknowledged"


# --- notifier -----------------------------------------------------------------------------


def _sns_event(msg: dict[str, Any]) -> dict[str, Any]:
    return {"Records": [{"Sns": {"Message": json.dumps(msg)}}]}


def test_notifier_sends_push_and_email(seeded, monkeypatch):
    pushes: list[tuple] = []
    monkeypatch.setattr(notifier, "send_ntfy", lambda *a: pushes.append(a))
    ses = boto3.client("sesv2")
    ses.create_email_identity(EmailIdentity="nightwatch@example.com")
    msg = {"kind": "notify", "household_id": "hh_demo", "incident_id": "inc_1",
           "contact_id": "c_priya", "title": "Red Flag Warning", "body": "Body —Night Watch",
           "priority": "default"}  # fmt: skip
    monkeypatch.setattr(
        notifier, "_deps", lambda: (seeded, "nw-topic", ses, "nightwatch@example.com")
    )
    assert notifier.handler(_sns_event(msg), None) == {
        "delivered": [{"push": "sent", "email": "sent"}]
    }
    assert pushes == [("nw-topic", "Red Flag Warning", "Body —Night Watch", "default")]


def test_notifier_fails_when_no_channel_delivers(seeded, monkeypatch):
    def boom(*a):
        raise TimeoutError("ntfy slow")

    monkeypatch.setattr(notifier, "send_ntfy", boom)
    seeded.put_contact(demo_contact(None))  # push only
    monkeypatch.setattr(notifier, "_deps", lambda: (seeded, "nw-topic", None, None))
    msg = {"kind": "notify", "household_id": "hh_demo", "incident_id": "inc_1",
           "contact_id": "c_priya", "title": "t", "body": "b", "priority": "default"}  # fmt: skip
    with pytest.raises(RuntimeError, match="no channel delivered"):
        notifier.handler(_sns_event(msg), None)


def test_sms_is_a_stub():
    from nightwatch_core.models import ContactChannels

    contact = demo_contact(None).model_copy(
        update={"channels": ContactChannels(sms="+15555550100")}
    )
    msg = {"title": "t", "body": "b", "priority": "default"}
    assert notifier.deliver(msg, contact, None, None, None) == {"sms": "stub: not sent"}
