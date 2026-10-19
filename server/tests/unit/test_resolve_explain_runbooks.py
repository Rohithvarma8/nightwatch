from datetime import UTC, datetime

import pytest

from nightwatch.domain.explain import explain, spoken_explanation
from nightwatch.domain.incidents import candidates
from nightwatch.domain.resolve import match_reference, not_found_message
from nightwatch.domain.runbooks import load_runbooks, runbook_for

from .helpers import incident

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
FIRE = incident("fire", "Fire risk", "high", supporting="Wind Advisory")
HEAT = incident("heat", "Heat Advisory", "moderate")
REPLAY = incident("rp", "Red Flag Warning", "high", replay=True)
PROD = incident("prod", "checkout-service latency", "moderate", kind="prod")
ALL = candidates([FIRE, HEAT, REPLAY, PROD], NOW)


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("the fire one", "fire"),
        ("the wind thing", "fire"),  # the wind advisory is part of the fire risk incident
        ("red flag", "fire"),  # live beats replay on a tie
        ("the hot one", "heat"),
        ("is it hot", "heat"),
        ("the checkout alarm", "prod"),
        ("the deploy", "prod"),
        ("the flood one", None),
    ],
)
def test_fuzzy_reference(reference, expected) -> None:
    found = match_reference(ALL, reference)
    assert (found.id if found else None) == expected


def test_not_found_lists_active_without_ids() -> None:
    msg = not_found_message("the flood one", ALL)
    assert msg.startswith("I couldn't find an incident matching 'the flood one'. Active right now:")
    assert "Replayed alert: Red Flag Warning" in msg and "fire" not in msg.split(":")[0]
    assert "inc_" not in msg


def test_explain_brief_and_full() -> None:
    brief = explain(FIRE, "brief")
    assert brief.what_happened == "Details of Fire risk."
    assert brief.what_it_means_for_you.startswith("Dry air and strong wind together")
    assert brief.confidence == "high" and brief.sources == ["National Weather Service"]
    assert [t.event for t in brief.timeline] == [
        "National Weather Service issued Red Flag Warning",
        "National Weather Service issued Wind Advisory",
    ]
    assert len(explain(FIRE, "full").evidence) >= len(brief.evidence)
    text = spoken_explanation(FIRE, brief)
    assert "Based on: NWS Fire risk." in text and "inc_" not in text


@pytest.mark.parametrize(
    ("certainty", "expected"), [("Observed", "high"), ("Possible", "medium"), ("Unlikely", "low")]
)
def test_confidence_from_certainty(certainty, expected) -> None:
    assert (
        explain(incident("x", "Wind Advisory", certainty=certainty), "brief").confidence == expected
    )


@pytest.mark.parametrize(
    ("inc", "runbook_id"),
    [
        (FIRE, "fire-risk"),
        (incident("r", "Red Flag Warning"), "red-flag-warning"),
        (incident("w", "Wind Advisory", "moderate"), "wind-advisory"),
        (HEAT, "heat"),
        (PROD, "deploy-regression"),
        (incident("o", "Tsunami Warning"), None),
    ],
)
def test_runbook_mapping(inc, runbook_id) -> None:
    book = runbook_for(inc, load_runbooks())
    assert (book.id if book else None) == runbook_id


def test_all_runbooks_load_with_why() -> None:
    books = load_runbooks()
    assert set(books) == {
        "red-flag-warning", "fire-risk", "wind-advisory", "heat", "poor-air-quality",
        "deploy-regression",
    }  # fmt: skip
    assert all(s.action and s.why for b in books.values() for s in b.steps)


def test_explain_and_runbook_text_have_no_doubled_periods() -> None:
    from nightwatch.tools.runbooks import _spoken, _view

    ai = FIRE.model_copy(update={"recommended_actions": ["Avoid activities that can spark fires."]})
    exp = explain(ai, "brief")
    assert ".." not in exp.what_it_means_for_you and ".." not in spoken_explanation(ai, exp)
    book = runbook_for(ai, load_runbooks())
    assert book is not None
    text = _spoken(_view(book, ai.id, ai.title), "fire risk")
    assert ".." not in text and text.startswith("For the fire risk: first, avoid anything")
