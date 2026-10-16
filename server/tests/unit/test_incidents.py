from datetime import UTC, datetime

import pytest

from nightwatch.domain.fixtures import FIXTURE_INCIDENTS
from nightwatch.domain.incidents import (
    build_active_incidents,
    overview,
    rank,
    select_active,
    spoken_overview,
)

from .helpers import incident

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("scope", "min_severity", "limit", "expected"),
    [
        ("all", "low", 3, ["Red Flag Warning", "checkout-service latency"]),
        ("home", "low", 3, ["Red Flag Warning"]),
        ("work", "low", 3, ["checkout-service latency"]),
        ("all", "high", 3, ["Red Flag Warning"]),
        ("all", "critical", 3, []),
        ("all", "low", 1, ["Red Flag Warning"]),
    ],
)
def test_select_active(scope, min_severity, limit, expected) -> None:
    got = select_active(overview(FIXTURE_INCIDENTS, NOW), scope, min_severity, limit)
    assert [i.title for i in got] == expected


def test_rank_severity_then_most_recent() -> None:
    older_high = incident("a", "Red Flag Warning", "high", started_at="2026-10-16T01:00:00Z")
    newer_high = incident("b", "Heat Advisory", "high", started_at="2026-10-16T05:00:00Z")
    moderate = incident("c", "Wind Advisory", "moderate", started_at="2026-10-16T09:00:00Z")
    assert [i.id for i in rank([moderate, older_high, newer_high])] == ["b", "a", "c"]


@pytest.mark.parametrize(
    ("incidents", "expected"),
    [
        # Live fire risk shadows a replayed red flag warning (same hazard family).
        (
            [incident("live", "Fire risk", supporting="Wind Advisory"),
             incident("rp", "Red Flag Warning", replay=True)],
            ["live"],
        ),
        # Replay is the only fire-weather data → shown.
        ([incident("rp", "Red Flag Warning", replay=True)], ["rp"]),
        # A live heat advisory doesn't hide a replayed red flag warning.
        (
            [incident("heat", "Heat Advisory", "moderate"),
             incident("rp", "Red Flag Warning", replay=True)],
            ["rp", "heat"],
        ),
        # Ended incidents drop out even before the sweep resolves them.
        ([incident("old", "Wind Advisory", ends_at="2026-10-16T11:00:00Z")], []),
    ],
)  # fmt: skip
def test_overview_replay_rules(incidents, expected) -> None:
    assert [i.id for i in overview(incidents, NOW)] == expected


def test_replay_label_is_a_short_prefix() -> None:
    rp = incident("rp", "Red Flag Warning", replay=True)
    result = build_active_incidents([rp], "Demo Household", "2026-10-16T12:00:00Z")
    assert result.spoken_overview.startswith("One thing. 1. Replayed alert: Red Flag Warning, high")
    view = result.incidents[0]
    assert view.replay is True and view.replay_original_time == "2026-10-15T20:16:00Z"
    assert not view.spoken_summary.startswith("Replay")


def test_spoken_overview_empty() -> None:
    assert spoken_overview([]) == "All clear. No active incidents right now."


def test_spoken_overview_has_no_ids() -> None:
    text = build_active_incidents(FIXTURE_INCIDENTS, "Demo Household", "x").spoken_overview
    assert text.startswith("Two things.")
    assert "inc_" not in text
