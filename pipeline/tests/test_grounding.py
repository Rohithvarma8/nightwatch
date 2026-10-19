"""Grounding check: output may only contain numbers, times, and names present in the source."""

import pytest

from nightwatch_pipeline.triage.grounding import check

SOURCE = (
    "HEADLINE: Red Flag Warning issued October 15 at 1:16PM PDT until October 17 at 8:00PM PDT "
    "by NWS Los Angeles/Oxnard CA\n"
    "DESCRIPTION: ...HIGH RISK FOR RAPID FIRE GROWTH THROUGH SATURDAY, DUE TO MODERATE TO "
    "LOCALLY STRONG SANTA ANA WINDS AND LOW RELATIVE HUMIDITY... Humidities 8 to 15 percent. "
    "Red Flag Warnings for most of Los Angeles and Ventura Counties through Saturday.\n"
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
        # Seen live from Nova Lite: coordination rephrased, both names in the source.
        "Fire danger is high across Ventura and Los Angeles Counties.",
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
        ("It also covers Kern and Ventura Counties.", "name 'Kern'"),  # invented county
    ],
)
def test_invented_facts_are_rejected(text: str, violation: str) -> None:
    result = check([text], SOURCE)
    assert not result.passed
    assert any(violation in v for v in result.violations), result.violations


# --- replay strict mode -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "violation"),
    [
        ("Fire danger stays high until Saturday evening.", "replay timing 'saturday'"),
        ("The warning runs through October 17.", "replay timing 'october'"),
        ("Strong winds are expected tonight.", "replay timing 'tonight'"),
        ("Gusts ease this afternoon.", "replay timing 'afternoon'"),
        ("The warning ends at 8 PM.", "replay clock time '8 PM'"),
        ("The warning ends at 8:00PM PDT.", "replay clock time '8:00PM'"),
        ("Issued 10/15 by the weather service.", "replay date '10/15'"),
    ],
)
def test_strict_mode_rejects_any_timing(text: str, violation: str) -> None:
    result = check([text], SOURCE, strict=True)
    assert not result.passed
    assert any(violation in v for v in result.violations), result.violations


def test_strict_mode_allows_timeless_text() -> None:
    text = "Strong Santa Ana winds and very dry air mean any spark could start a fast fire."
    assert check([text], SOURCE, strict=True).passed


def test_strict_off_keeps_grounded_days() -> None:
    assert check(["Fire danger stays high through Saturday."], SOURCE).passed


# --- URLs / domains -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("See readyforwildfire.org for tips.", True),
        ("Visit https://weather.gov now.", True),
        ("Check www.example.com", True),
        ("Go to wildfirerisk.org/plan", True),
        ("Keep windows closed.", False),
        ("Humidity near 8.5 percent.", False),
        ("Leave by 8 p.m. if told to.", False),
        ("Follow U.S. Forest Service guidance.", False),
    ],
)
def test_has_url(text: str, expected: bool) -> None:
    from nightwatch_pipeline.triage.grounding import has_url

    assert has_url(text) is expected
