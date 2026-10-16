"""Deterministic summaries. Used until the Day 4 triage agent, and as its fallback after.

Only facts from the signal: event name, place name, and end time. No invented numbers.
"""

from datetime import datetime

from nightwatch_core.models import HazardFamily, Household, Signal
from nightwatch_core.timefmt import spoken_until

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


def recommended_actions(signal: Signal) -> list[str]:
    return _EVENT_ACTIONS.get(signal.event) or _FAMILY_ACTIONS[signal.hazard_family]


def spoken_summary(signal: Signal, household: Household, now: datetime) -> str:
    until = spoken_until(signal.ends_at, household.tz, now)
    text = (
        f"The National Weather Service has {_article(signal.event)} {signal.event} "
        f"for {signal.area_name} until {until}."
    )
    return f"Replay of a real alert. {text}" if signal.replay else text


def detail_summary(signal: Signal) -> str:
    return signal.headline
