from datetime import datetime

import pytest

from nightwatch_core.ids import new_id, ulid
from nightwatch_core.keys import active_gsi1_sk
from nightwatch_core.timefmt import spoken_until, to_utc_iso

TZ = "America/Los_Angeles"
NOW = datetime.fromisoformat("2026-10-15T18:00:00-07:00")  # Thursday


@pytest.mark.parametrize(
    ("ends_at", "expected"),
    [
        ("2026-10-16T03:00:00Z", "8 PM Thursday"),  # same day: still absolute
        ("2026-10-16T19:30:00Z", "12:30 PM Friday"),
        ("2026-10-18T03:00:00Z", "8 PM Saturday"),
        ("2026-10-30T03:00:00Z", "8 PM October 29"),
    ],
)
def test_spoken_until(ends_at, expected) -> None:
    assert spoken_until(ends_at, TZ, NOW) == expected


def test_to_utc_iso() -> None:
    assert to_utc_iso("2026-10-17T20:00:00-07:00") == "2026-10-18T03:00:00Z"
    with pytest.raises(ValueError):
        to_utc_iso("2026-10-17T20:00:00")


def test_ids_and_sort_key() -> None:
    assert len(ulid()) == 26 and ulid(0)[:10] == "0000000000"
    assert new_id("inc").startswith("inc_")
    assert active_gsi1_sk("critical", "2026-10-15T00:00:00Z") < active_gsi1_sk(
        "high", "2026-10-14T00:00:00Z"
    )
