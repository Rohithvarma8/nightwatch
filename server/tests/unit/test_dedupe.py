import pytest

from nightwatch.domain.dedupe import covers
from nightwatch.domain.explain import explain, timeline_event
from nightwatch.domain.incidents import (
    build_active_incidents,
    do_now,
    spoken_action,
    spoken_overview,
    to_view,
)
from nightwatch_core.models import Incident, SignalRef

from .helpers import incident

# Live 2026-10-20: the triage summary and its top action said the same thing.
LIVE_SUMMARY = (
    "Red Flag Warning in effect. High risk for rapid fire growth due to strong Santa Ana winds "
    "and low humidity. Be extremely cautious with anything that can spark. In effect until "
    "12:07 AM Friday."
)
LIVE_TOP = "Use extreme caution with anything that can spark a wildfire"
LIVE_NEXT = "Prepare to evacuate if a wildfire breaks out in your area"
FIRE_STEPS = [
    "Avoid anything that could spark a fire, like mowing, grilling, or parking on dry grass",
    "Bring in or tie down loose outdoor items and cushions",
]


@pytest.mark.parametrize(
    ("summary", "action", "expected"),
    [
        (LIVE_SUMMARY, LIVE_TOP, True),
        (LIVE_SUMMARY, LIVE_NEXT, False),
        (LIVE_SUMMARY, FIRE_STEPS[1], False),
        ("Stay indoors. Keep windows closed.", "Keep your windows closed", False),  # < 3 words
        ("Avoid outdoor burning tonight.", "Avoid any outdoor burning until Friday", False),
        (
            "Gusts to 60 mph. Secure loose outdoor furniture and trash cans.",
            "Secure loose outdoor furniture",
            True,
        ),
        ("Latency is up after a deploy.", "Roll back checkout-service to v4", False),
        ("", LIVE_TOP, False),
        (LIVE_SUMMARY, "", False),
    ],
)
def test_covers(summary: str, action: str, expected: bool) -> None:
    assert covers(summary, action) is expected


def test_covers_ignores_title_words() -> None:
    summary = "Red Flag Warning in effect until 8 PM."
    assert covers(summary, "Act on the Red Flag Warning") is True
    assert covers(summary, "Act on the Red Flag Warning", title="Red Flag Warning") is False


def _live(**update: object) -> Incident:
    base = incident("inc_live", "Red Flag Warning")
    fields = {"spoken_summary": LIVE_SUMMARY, "recommended_actions": [LIVE_TOP, LIVE_NEXT]}
    return base.model_copy(update={**fields, **update})


def test_spoken_overview_drops_a_caution_the_summary_already_has() -> None:
    text = spoken_overview([_live()])
    assert text.count("spark") == 1
    assert "Use extreme caution" not in text
    assert spoken_action(_live()) == ""


def test_spoken_overview_keeps_a_new_action() -> None:
    inc = _live(recommended_actions=[LIVE_NEXT])
    assert spoken_overview([inc]).endswith(f"{LIVE_NEXT}.")


def test_do_now_skips_covered_actions_then_runbook_steps() -> None:
    assert do_now(_live(), FIRE_STEPS) == LIVE_NEXT
    only_dup = _live(recommended_actions=[LIVE_TOP])
    # The first runbook step mentions sparks but not caution: it's new advice.
    assert do_now(only_dup, FIRE_STEPS) == FIRE_STEPS[0]
    assert do_now(only_dup, []) == ""
    assert to_view(only_dup, FIRE_STEPS).top_action == FIRE_STEPS[0]


def test_do_now_keeps_the_pinned_prod_action() -> None:
    prod = incident("inc_p", "checkout-service latency", kind="prod").model_copy(
        update={
            "spoken_summary": "Roll back checkout-service to v4 now.",
            "recommended_actions": ["Roll back checkout-service to v4"],
        }
    )
    assert do_now(prod, ["Check the dashboard"]) == "Roll back checkout-service to v4"


def test_active_incidents_view_and_overview_agree() -> None:
    result = build_active_incidents([_live()], "Demo Household", "2026-10-20T10:00:00Z")
    assert result.incidents[0].top_action == LIVE_NEXT
    assert "Use extreme caution" not in result.spoken_overview


def test_explain_meaning_drops_the_duplicate_and_has_the_card_header() -> None:
    exp = explain(_live(), "brief", "Demo Household", "2026-10-20T10:00:00Z", FIRE_STEPS)
    assert "Use extreme caution" not in exp.what_it_means_for_you
    assert exp.incident.top_action == LIVE_NEXT
    assert (exp.household, exp.as_of) == ("Demo Household", "2026-10-20T10:00:00Z")


def _ref(source: str, message_type: str, summary: str, event: str | None) -> SignalRef:
    return SignalRef(
        source=source,  # type: ignore[arg-type]
        external_id="x",
        observed_at="2026-10-20T10:00:00Z",
        summary=summary,
        url="https://example.com",
        event=event,
        message_type=message_type,
    )


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        (
            _ref(
                "codedeploy",
                "Alert",
                "Deployment d-RHIE8LKLL of checkout-service from version 4 to 5 succeeded.",
                "Deployment",
            ),
            "Deployment v4→v5 of checkout-service finished",
        ),
        (_ref("codedeploy", "Alert", "Something else", "Deployment"), "Deployment finished"),
        (
            _ref("cloudwatch", "Alert", "x is ALARM", "checkout-service latency"),
            "checkout-service latency alarm went into ALARM",
        ),
        (
            _ref("cloudwatch", "Cancel", "x is OK", "checkout-service latency"),
            "checkout-service latency alarm returned to OK",
        ),
        (
            _ref("nws", "Update", "Red Flag Warning", "Red Flag Warning"),
            "National Weather Service updated Red Flag Warning",
        ),
    ],
)
def test_timeline_wording_per_source(ref: SignalRef, expected: str) -> None:
    assert timeline_event(ref) == expected
