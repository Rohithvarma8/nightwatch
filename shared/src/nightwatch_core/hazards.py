"""Hazard family and severity for NWS alerts. Deterministic, table-driven."""

from nightwatch_core.models import SEVERITY_RANK, HazardFamily, Severity

_FAMILY: dict[str, HazardFamily] = {
    "Red Flag Warning": "fire_weather",
    "Fire Weather Watch": "fire_weather",
    "Fire Warning": "fire_weather",
    "Extreme Fire Danger": "fire_weather",
    "High Wind Warning": "wind",
    "High Wind Watch": "wind",
    "Wind Advisory": "wind",
    "Extreme Wind Warning": "wind",
    "Lake Wind Advisory": "wind",
    "Excessive Heat Warning": "heat",
    "Excessive Heat Watch": "heat",
    "Extreme Heat Warning": "heat",
    "Extreme Heat Watch": "heat",
    "Heat Advisory": "heat",
    "Freeze Warning": "cold",
    "Freeze Watch": "cold",
    "Frost Advisory": "cold",
    "Beach Hazards Statement": "coastal",
    "Coastal Flood Advisory": "coastal",
    "High Surf Advisory": "coastal",
    "Air Quality Alert": "air",
    "Dense Smoke Advisory": "air",
}

# Events whose household impact is fixed regardless of the CAP fields.
_EVENT_SEVERITY: dict[str, Severity] = {
    "Red Flag Warning": "high",
    "Fire Warning": "critical",
    "Evacuation Immediate": "critical",
    "Extreme Wind Warning": "critical",
    "Tornado Warning": "critical",
}

_CAP_SEVERITY: dict[str, Severity] = {
    "Extreme": "critical",
    "Severe": "high",
    "Moderate": "moderate",
    "Minor": "low",
}

_LOW_CONFIDENCE = {"Possible", "Unlikely"}
_NOT_NOW = {"Future", "Past"}
_ORDER: list[Severity] = ["critical", "high", "moderate", "low"]


def hazard_family(event: str) -> HazardFamily:
    return _FAMILY.get(event, "other")


def _cap(severity: Severity, ceiling: Severity) -> Severity:
    return severity if SEVERITY_RANK[severity] >= SEVERITY_RANK[ceiling] else ceiling


def _down(severity: Severity) -> Severity:
    return _ORDER[min(SEVERITY_RANK[severity] + 1, len(_ORDER) - 1)]


def nws_severity(event: str, severity: str, urgency: str, certainty: str) -> Severity:
    """Map NWS CAP fields + event type to our four levels.

    1. Fixed events win (Red Flag Warning = high).
    2. Otherwise CAP severity (Extreme/Severe/Moderate/Minor; Unknown = low),
       one level lower if urgency is Future/Past or certainty is Possible/Unlikely.
    3. Watches and advisories cap at moderate; statements cap at low.
    """
    if event in _EVENT_SEVERITY:
        return _EVENT_SEVERITY[event]
    level = _CAP_SEVERITY.get(severity, "low")
    if urgency in _NOT_NOW or certainty in _LOW_CONFIDENCE:
        level = _down(level)
    if event.endswith(("Watch", "Advisory")):
        level = _cap(level, "moderate")
    elif event.endswith("Statement"):
        level = "low"
    return level
