"""Deterministic summaries: the default until the triage agent runs, and its fallback after.

Only facts from the signals: event names, the place name, and end times. No invented numbers.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from nightwatch_core.models import HazardFamily, Household, Signal, Summarizer
from nightwatch_core.timefmt import spoken_until

if TYPE_CHECKING:
    from nightwatch_pipeline.triage.rules import Proximity

TEMPLATE_MODEL = "template-v1"

_EVENT_ACTIONS: dict[str, list[str]] = {
    "Red Flag Warning": [
        "Avoid anything that could spark a fire",
        "Be ready to leave quickly if a fire starts nearby",
    ],
    "Fire Weather Watch": ["Plan to avoid outdoor sparks in the coming days"],
    "High Wind Warning": ["Secure outdoor items and stay away from trees and power lines"],
    "Wind Advisory": ["Secure loose outdoor items"],
}
_FIRE_RISK_ACTIONS = [
    "Avoid anything that could spark a fire",
    "Secure loose outdoor items",
    "Be ready to leave quickly if a fire starts nearby",
]
_FAMILY_ACTIONS: dict[HazardFamily, list[str]] = {
    "fire_weather": ["Avoid anything that could spark a fire"],
    "wind": ["Secure loose outdoor items"],
    "heat": ["Stay cool and check on people who are vulnerable to heat"],
    "cold": ["Protect pipes, plants, and pets from the cold"],
    "coastal": ["Stay off the beach and out of the water"],
    "air": ["Keep windows closed and limit time outside"],
    "other": ["Follow the National Weather Service instructions"],
}


def _article(word: str) -> str:
    return "an" if word[:1].upper() in "AEIOU" else "a"


def recommended_actions(primary: Signal, supporting: Signal | None = None) -> list[str]:
    if supporting is not None:
        return _FIRE_RISK_ACTIONS
    return _EVENT_ACTIONS.get(primary.event) or _FAMILY_ACTIONS[primary.hazard_family]


def spoken_summary(
    primary: Signal, supporting: Signal | None, household: Household, now: datetime
) -> str:
    until = spoken_until(primary.ends_at, household.tz, now)
    text = (
        f"The National Weather Service has {_article(primary.event)} {primary.event} "
        f"for {primary.area_name} until {until}"
    )
    if supporting is not None:
        also = spoken_until(supporting.ends_at, household.tz, now)
        text += f", and {_article(supporting.event)} {supporting.event} until {also}"
    return text + "."


def detail_summary(primary: Signal, supporting: Signal | None = None) -> str:
    return primary.headline if supporting is None else f"{primary.headline} {supporting.headline}"


def summarizer() -> Summarizer:
    return Summarizer(model=TEMPLATE_MODEL, latency_ms=0, fallback_used=False)


# --- prod (alarm + deploy) ------------------------------------------------------------------


def prod_spoken_summary(alarm: Signal, proximity: "Proximity | None") -> str:
    """No IDs (spoken). Numbers come from the alarm and deploy facts."""
    service = alarm.area_name
    if proximity is not None:
        a = proximity.deploy.attributes
        unit = "minute" if proximity.minutes == 1 else "minutes"
        return (
            f"{service} latency rose above its alarm threshold {proximity.minutes} {unit} after "
            f"a deploy from version {a['from_version']} to {a['to_version']}."
        )
    threshold = alarm.attributes.get("threshold")
    limit = f" of {threshold} milliseconds" if threshold else ""
    return f"{service} latency is above its alarm threshold{limit}."


def prod_detail_summary(alarm: Signal, proximity: "Proximity | None") -> str:
    text = alarm.headline
    if proximity is not None:
        text += f" {proximity.deploy.headline}"
    return text


def prod_actions(alarm: Signal, proximity: "Proximity | None") -> list[str]:
    if proximity is not None:
        return [
            "Roll back the latest deploy",
            f"Watch the {alarm.area_name} latency alarm after the rollback",
        ]
    return [f"Check the {alarm.area_name} dashboard and recent changes"]
