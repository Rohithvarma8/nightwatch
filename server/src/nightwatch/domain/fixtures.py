"""Hard-coded incidents for tests and for `make run` without a table (NIGHTWATCH_TABLE unset)."""

from datetime import datetime

from nightwatch.domain.models import IncidentView

FIXTURE_INCIDENTS: list[IncidentView] = [
    IncidentView(
        id="inc_01JZ8Q4D7M3V6B2N9K5T1R0XYA",
        kind="hazard",
        title="Red Flag Warning",
        severity="high",
        status="open",
        started_at="2026-10-21T09:14:00Z",
        spoken_summary=(
            "The National Weather Service issued a red flag warning for your county "
            "until 6 PM, with gusty winds and low humidity."
        ),
        top_action="Keep windows closed",
        evidence_preview=["NWS warning, county-wide", "AQI 78 (moderate)"],
        escalation_due_at=None,
        replay=False,
        replay_original_time=None,
    ),
    IncidentView(
        id="inc_01JZ8Q6F2C8H4W7P3S9D5G1XYB",
        kind="prod",
        title="checkout-service latency",
        severity="moderate",
        status="open",
        started_at="2026-10-21T09:51:00Z",
        spoken_summary=(
            "Checkout latency rose above its alarm threshold four minutes after a deploy "
            "from version 42 to 43."
        ),
        top_action="Roll back the latest deploy",
        evidence_preview=["p95 latency alarm in ALARM", "Deploy v42 to v43, 4 min earlier"],
        escalation_due_at="2026-10-21T09:56:00Z",
        replay=False,
        replay_original_time=None,
    ),
]


class FixtureSource:
    def household_name(self) -> str:
        return "Demo Household"

    def active_incidents(self, now: datetime) -> list[IncidentView]:
        return FIXTURE_INCIDENTS
