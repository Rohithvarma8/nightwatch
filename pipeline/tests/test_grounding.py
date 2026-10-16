"""Grounding check: output may only contain numbers, times, and names present in the source."""

import pytest

from nightwatch_pipeline.triage.grounding import check

SOURCE = (
    "HEADLINE: Red Flag Warning issued October 15 at 1:16PM PDT until October 17 at 8:00PM PDT "
    "by NWS Los Angeles/Oxnard CA\n"
    "DESCRIPTION: ...HIGH RISK FOR RAPID FIRE GROWTH THROUGH SATURDAY, DUE TO MODERATE TO "
    "LOCALLY STRONG SANTA ANA WINDS AND LOW RELATIVE HUMIDITY... Humidities 8 to 15 percent.\n"
    "EVIDENCE: NWS Red Flag Warning, Southeastern Ventura County Valleys"
)


@pytest.mark.parametrize(
    "text",
    [
        "A Red Flag Warning is in effect for Southeastern Ventura County Valleys until 8 PM "
        "October 17.",
        "Strong Santa Ana winds and humidity as low as 8 percent make fires spread fast.",
        "Gusty Santa Ana winds continue through Saturday.",
        "Avoid anything that could spark a fire.",
    ],
)
def test_grounded_text_passes(text: str) -> None:
    assert check([text], SOURCE).passed, check([text], SOURCE).violations


@pytest.mark.parametrize(
    ("text", "violation"),
    [
        ("Winds could gust to 60 mph tonight.", "number '60'"),  # invented number
        ("Humidity may drop to five percent.", "number '5'"),  # spelled-out invented number
        ("The warning lasts until Sunday.", "time word 'sunday'"),  # invented day
        ("It ends tomorrow evening.", "time word 'tomorrow'"),  # relative day not in source
        ("Fire risk is high near Thousand Oaks.", "name 'Thousand Oaks'"),  # invented place
    ],
)
def test_invented_facts_are_rejected(text: str, violation: str) -> None:
    result = check([text], SOURCE)
    assert not result.passed
    assert any(violation in v for v in result.violations), result.violations
