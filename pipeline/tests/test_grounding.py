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


# Seen live on 2026-10-20 (Nova Lite and Claude Haiku 4.5 replays): a sentence ending in
# "Ventura Counties." ran into the next sentence's first word ("Ventura Counties Winds").
BOUNDARY = "Red Flag Warnings cover most of Los Angeles and Ventura Counties."


@pytest.mark.parametrize(
    "text",
    [
        f"{BOUNDARY} Winds and low humidity make fires spread fast.",
        f"{BOUNDARY} Use extreme caution with anything that could spark a fire.",
        f"{BOUNDARY} If a fire starts, it could spread rapidly.",
        f"{BOUNDARY} Conditions favor rapid fire growth.",
    ],
)
def test_sentence_boundary_ends_a_name(text: str) -> None:
    assert check([text], SOURCE).passed, check([text], SOURCE).violations


def test_invented_name_after_a_sentence_boundary_is_rejected() -> None:
    result = check([f"{BOUNDARY} Winds also reach Thousand Oaks."], SOURCE)
    assert result.violations == ["name 'Thousand Oaks' not in source"]


ABBREVIATION_SOURCE = "Smoke from a U.S. Forest Service burn near Mt. Pinos may drift east."


@pytest.mark.parametrize(
    "text", ["Smoke from the U.S. Forest Service burn may drift.", "Smoke near Mt. Pinos."]
)
def test_abbreviations_stay_part_of_a_name(text: str) -> None:
    assert check([text], ABBREVIATION_SOURCE).passed, check([text], ABBREVIATION_SOURCE).violations


@pytest.mark.parametrize(
    ("text", "violation"),
    [
        ("Smoke from the U.S. Park Service burn may drift.", "name 'U.S. Park'"),
        ("Smoke near Mt. Wilson.", "name 'Mt. Wilson'"),
    ],
)
def test_invented_names_with_abbreviations_are_rejected(text: str, violation: str) -> None:
    result = check([text], ABBREVIATION_SOURCE)
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


@pytest.mark.parametrize(
    "text",
    [
        "Strong Santa Ana winds and very dry air mean any spark could start a fast fire.",
        # Seen live from Nova Lite: "may" is the verb here, not the month.
        "Wind Advisory: Gusty winds may cause unsecured objects to blow around.",
        "May be windy near the foothills.",
    ],
)
def test_strict_mode_allows_timeless_text(text: str) -> None:
    result = check([text], SOURCE, strict=True)
    assert result.passed, result.violations


@pytest.mark.parametrize(
    "text",
    ["The warning lasts until May 3.", "It began on 12 March.", "Expect this, in May, again."],
)
def test_strict_mode_still_rejects_may_and_march_as_months(text: str) -> None:
    assert not check([text], SOURCE, strict=True).passed


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
