"""Hard-coded incidents for tests and for `make run` without a table (NIGHTWATCH_TABLE unset)."""

from datetime import datetime

from nightwatch_core.models import (
    Contact,
    ContactChannels,
    DeployRecord,
    EscalationPolicy,
    Evidence,
    Incident,
    SignalRef,
    Summarizer,
)
from nightwatch_core.timefmt import to_utc_iso

_TEMPLATE = Summarizer(model="template-v1", latency_ms=0, fallback_used=False)

FIXTURE_INCIDENTS: list[Incident] = [
    Incident(
        id="inc_01JZ8Q4D7M3V6B2N9K5T1R0XYA",
        household_id="hh_demo",
        kind="hazard",
        title="Red Flag Warning",
        severity="high",
        status="open",
        started_at="2026-10-21T09:14:00Z",
        updated_at="2026-10-21T09:14:00Z",
        ends_at="2099-01-01T00:00:00Z",
        correlation_key="hh_demo#fire_weather#CAZ374",
        signals=[
            SignalRef(
                source="nws",
                external_id="urn:oid:fixture.rfw",
                observed_at="2026-10-21T09:14:00Z",
                summary="Red Flag Warning issued October 21 until October 21 at 6:00PM PDT",
                url="https://api.weather.gov/alerts/urn:oid:fixture.rfw",
                event="Red Flag Warning",
                hazard_family="fire_weather",
                message_type="Alert",
                certainty="Likely",
            )
        ],
        evidence=[
            Evidence(type="nws_alert", detail="NWS warning, county-wide", weight=1.0),
            Evidence(type="aqi_category", detail="AQI 78 (moderate)", weight=0.4),
        ],
        spoken_summary=(
            "The National Weather Service issued a red flag warning for your county "
            "until 6 PM, with gusty winds and low humidity."
        ),
        detail_summary="Red Flag Warning issued October 21 until October 21 at 6:00PM PDT.",
        recommended_actions=["Keep windows closed"],
        area_name="Southeastern Ventura County Valleys",
        escalation_due_at="2099-01-01T00:00:00Z",
        summarizer=_TEMPLATE,
    ),
    Incident(
        id="inc_01JZ8Q6F2C8H4W7P3S9D5G1XYB",
        household_id="hh_demo",
        kind="prod",
        title="checkout-service latency",
        severity="moderate",
        status="open",
        started_at="2026-10-21T09:51:00Z",
        updated_at="2026-10-21T09:51:00Z",
        ends_at="2099-01-01T00:00:00Z",
        correlation_key="hh_demo#prod#checkout-service",
        signals=[
            SignalRef(
                source="cloudwatch",
                external_id="fixture.alarm",
                observed_at="2026-10-21T09:51:00Z",
                summary="checkout-service p95 latency alarm in ALARM",
                url="https://console.aws.amazon.com/cloudwatch/",
                message_type="Alert",
            )
        ],
        evidence=[
            Evidence(type="alarm", detail="p95 latency alarm in ALARM", weight=1.0),
            Evidence(
                type="deploy_proximity",
                detail="Latency rose 4 minutes after deployment d-AB12CD34E (v42→v43); "
                "no other service changed",
                weight=0.6,
                spoken="Latency rose 4 minutes after a deploy from version 42 to 43",
            ),
        ],
        spoken_summary=(
            "Checkout latency rose above its alarm threshold four minutes after a deploy "
            "from version 42 to 43."
        ),
        detail_summary="The p95 latency alarm fired four minutes after deploy v42 to v43.",
        recommended_actions=["Roll back the latest deploy"],
        summarizer=_TEMPLATE,
    ),
]


FIXTURE_CONTACTS = [
    Contact(
        id="c_priya",
        household_id="hh_demo",
        name="Priya",
        aliases=["roommate"],
        channels=ContactChannels(ntfy=True, email="priya@example.com"),
        escalation_order=1,
    )
]


class FixtureSource:
    """In-memory source for tests and `make run` without a table. Writes stay in memory."""

    def __init__(self) -> None:
        self.incidents = {i.id: i.model_copy() for i in FIXTURE_INCIDENTS}
        self.events: list[tuple[str, str, dict[str, str]]] = []
        self.slots: dict[str, int] = {}

    def household_name(self) -> str:
        return "Demo Household"

    def household_tz(self) -> str:
        return "America/Los_Angeles"

    def contacts(self) -> list[Contact]:
        return FIXTURE_CONTACTS

    def escalation_policy(self) -> EscalationPolicy | None:
        return EscalationPolicy(household_id="hh_demo", contact_ids=["c_priya"])

    def active_incidents(self, now: datetime) -> list[Incident]:
        return list(self.incidents.values())

    def get_incident(self, incident_id: str) -> Incident | None:
        return self.incidents.get(incident_id)

    def _set(self, incident_id: str, **update: object) -> Incident:
        inc = self.incidents[incident_id].model_copy(update=update)
        self.incidents[incident_id] = inc
        return inc

    def acknowledge(self, incident_id: str, now: datetime) -> tuple[Incident | None, bool]:
        inc = self.incidents.get(incident_id)
        if inc is None or inc.status not in ("open", "escalated"):
            return inc, False
        return self._set(incident_id, status="acknowledged", acked_at=to_utc_iso(now)), True

    def mark_escalated(self, incident_id: str, now: datetime) -> Incident | None:
        inc = self.incidents.get(incident_id)
        if inc is None or inc.status == "resolved":
            return None
        return self._set(incident_id, status="escalated", escalated_at=to_utc_iso(now))

    def take_notify_slot(self, contact_id: str, now: datetime, limit: int) -> bool:
        key = f"{contact_id}#{now.strftime('%Y-%m-%dT%H')}"
        if self.slots.get(key, 0) >= limit:
            return False
        self.slots[key] = self.slots.get(key, 0) + 1
        return True

    def add_event(self, incident_id: str, event_type: str, now: datetime, **detail: str) -> None:
        self.events.append((incident_id, event_type, detail))

    def latest_deploy(self, service: str) -> DeployRecord | None:
        return None


class FixtureNotifier:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def publish(self, msg: dict) -> str:
        self.sent.append(msg)
        return f"fixture-{len(self.sent)}"
