"""Hard-coded incidents for tests and for `make run` without a table (NIGHTWATCH_TABLE unset)."""

from datetime import datetime

from nightwatch_core.models import Evidence, Incident, SignalRef, Summarizer

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
                type="deploy_proximity", detail="Deploy v42 to v43, 4 min earlier", weight=0.6
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


class FixtureSource:
    def household_name(self) -> str:
        return "Demo Household"

    def active_incidents(self, now: datetime) -> list[Incident]:
        return FIXTURE_INCIDENTS

    def get_incident(self, incident_id: str) -> Incident | None:
        return next((i for i in FIXTURE_INCIDENTS if i.id == incident_id), None)
