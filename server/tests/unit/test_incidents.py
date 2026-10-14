import pytest

from nightwatch.domain.fixtures import FIXTURE_INCIDENTS
from nightwatch.domain.incidents import select_active, spoken_overview


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
    got = select_active(FIXTURE_INCIDENTS, scope, min_severity, limit)
    assert [i.title for i in got] == expected


def test_spoken_overview_empty() -> None:
    assert spoken_overview([]) == "All clear. No active incidents right now."


def test_spoken_overview_has_no_ids() -> None:
    text = spoken_overview(FIXTURE_INCIDENTS)
    assert text.startswith("Two things.")
    assert "inc_" not in text
