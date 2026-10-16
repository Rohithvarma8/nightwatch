"""Replay one archived NWS alert through the live ingest path.

    python -m nightwatch_pipeline.replay <alert.json> --table <name> --bus <name>

The alert is time-shifted so it was "sent" now (onset/expires/ends move by the same offset),
marked replay=true with replay_original_time = the original `sent`, deduped, and put on the
bus exactly like live data. Each run gets its own external id, so it can be replayed again.
"""

import argparse
import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nightwatch_core.timefmt import to_utc_iso
from nightwatch_pipeline.bus import Bus
from nightwatch_pipeline.ingest.nws import ingest_features
from nightwatch_pipeline.store import Store

_TIME_FIELDS = ("sent", "effective", "onset", "expires", "ends")


def time_shift(feature: dict[str, Any], now: datetime) -> tuple[dict[str, Any], str]:
    """Copy of the feature with every timestamp moved so `sent` == now. Returns (copy, original)."""
    shifted = copy.deepcopy(feature)
    props = shifted["properties"]
    original = props["sent"]
    delta = now - datetime.fromisoformat(original)
    for field in _TIME_FIELDS:
        if props.get(field):
            props[field] = (datetime.fromisoformat(props[field]) + delta).isoformat()
    return shifted, original


def replay(path: Path, store: Store, bus: Bus, household_id: str, now: datetime) -> dict:
    feature = json.loads(path.read_text())
    household = store.get_household(household_id)
    if household is None:
        raise SystemExit(f"household {household_id} not found; run `make seed-household` first")
    shifted, original_sent = time_shift(feature, now)
    counts = ingest_features(
        [shifted],
        household,
        store,
        bus,
        now,
        external_id=f"replay:{feature['properties']['id']}:{to_utc_iso(now)}",
        replay=True,
        replay_original_time=to_utc_iso(original_sent),
    )
    return {"event": feature["properties"]["event"], "original_sent": original_sent, **counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--table", required=True)
    parser.add_argument("--bus", required=True)
    parser.add_argument("--household", default="hh_demo")
    args = parser.parse_args()
    result = replay(
        args.file.expanduser(), Store(args.table), Bus(args.bus), args.household, datetime.now(UTC)
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
