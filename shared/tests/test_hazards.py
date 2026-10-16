import pytest

from nightwatch_core.hazards import hazard_family, nws_severity


@pytest.mark.parametrize(
    ("event", "severity", "urgency", "certainty", "expected"),
    [
        ("Red Flag Warning", "Severe", "Expected", "Likely", "high"),
        ("Red Flag Warning", "Minor", "Future", "Possible", "high"),  # fixed by event type
        ("Fire Warning", "Severe", "Immediate", "Observed", "critical"),
        ("High Wind Warning", "Severe", "Expected", "Likely", "high"),
        ("High Wind Warning", "Extreme", "Immediate", "Observed", "critical"),
        ("High Wind Warning", "Severe", "Future", "Likely", "moderate"),  # not now → one lower
        ("High Wind Warning", "Severe", "Expected", "Possible", "moderate"),  # low confidence
        ("High Wind Watch", "Severe", "Future", "Possible", "moderate"),
        ("Fire Weather Watch", "Severe", "Expected", "Likely", "moderate"),  # watch cap
        ("Wind Advisory", "Moderate", "Expected", "Likely", "moderate"),
        ("Heat Advisory", "Minor", "Expected", "Likely", "low"),
        ("Beach Hazards Statement", "Moderate", "Expected", "Likely", "low"),
        ("Some New Event", "Unknown", "Unknown", "Unknown", "low"),
    ],
)
def test_nws_severity(event, severity, urgency, certainty, expected) -> None:
    assert nws_severity(event, severity, urgency, certainty) == expected


@pytest.mark.parametrize(
    ("event", "family"),
    [
        ("Red Flag Warning", "fire_weather"),
        ("Fire Weather Watch", "fire_weather"),
        ("Wind Advisory", "wind"),
        ("Heat Advisory", "heat"),
        ("Frost Advisory", "cold"),
        ("Tsunami Warning", "other"),
    ],
)
def test_hazard_family(event, family) -> None:
    assert hazard_family(event) == family
