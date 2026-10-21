"""DEV ONLY: reset to one fresh replayed Fire risk incident for recording.

    python -m nightwatch_pipeline.demo_reset --table <name> --bus <name> --rfw <a.json> \
        --wind <b.json> [--ack-timeout-s 120] --confirm

1. Delete incidents, OPENKEYs, signal records, and notify rate-limit counters (households,
   contacts, policies, and deploy records stay). Escalation timers of deleted incidents still
   fire, then find nothing ("noop: not found").
2. Re-seed the demo household (with the given ack timeout), contact, and escalation policy.
3. Replay an archived Red Flag Warning, wait for its incident, then replay an overlapping Wind
   Advisory for the same zone: the rules merge them into one "Fire risk" incident.
4. Wait for triage and the escalation timer, then print the incident and its due time.
"""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import boto3

from nightwatch_core.models import Incident
from nightwatch_pipeline.bus import Bus
from nightwatch_pipeline.cutover import is_derived
from nightwatch_pipeline.replay import replay
from nightwatch_pipeline.seed import DEMO_HOUSEHOLD, seed
from nightwatch_pipeline.store import Store
from nightwatch_pipeline.triage.rules import FIRE_EVENTS, FIRE_RISK_TITLE, WIND_EVENTS

ZONE = DEMO_HOUSEHOLD.forecast_zone.id


def is_reset_target(item: dict[str, Any]) -> bool:
    return is_derived(item) or str(item["PK"]).startswith("RATE#")


def check_alert(path: Path, events: frozenset[str]) -> str:
    """The archived alert must be one of `events` and cover the demo zone. Returns its event."""
    props = json.loads(path.read_text())["properties"]
    if props["event"] not in events or ZONE not in props.get("geocode", {}).get("UGC", []):
        raise SystemExit(f"{path}: {props['event']} is not one of {sorted(events)} for {ZONE}")
    return props["event"]


def delete_derived(table: Any) -> int:
    scan: dict[str, Any] = {"ProjectionExpression": "PK, SK"}
    deleted = 0
    with table.batch_writer() as batch:
        while True:
            page = table.scan(**scan)
            for item in page["Items"]:
                if is_reset_target(item):
                    batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
                    deleted += 1
            if "LastEvaluatedKey" not in page:
                return deleted
            scan["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def is_ready(inc: Incident) -> bool:
    """Merged, triaged for its current content, and escalation timer scheduled."""
    return (
        inc.title == FIRE_RISK_TITLE
        and inc.status == "open"
        and inc.escalation_due_at is not None
        and inc.summarizer.content_hash == inc.content_hash
    )


def wait_for(store: Store, done: Any, what: str, timeout_s: float) -> list[Incident]:
    deadline = time.monotonic() + timeout_s
    while True:
        active = store.list_active(DEMO_HOUSEHOLD.id)
        if done(active):
            return active
        if time.monotonic() > deadline:
            titles = [(i.title, i.status, i.summarizer.model) for i in active]
            raise SystemExit(f"timed out after {timeout_s:.0f}s waiting for {what}: {titles}")
        time.sleep(3)


def local(iso: str, tz: str) -> str:
    when = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ZoneInfo(tz))
    return when.strftime("%-I:%M:%S %p %Z")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", required=True)
    parser.add_argument("--bus", required=True)
    parser.add_argument("--rfw", type=Path, required=True)
    parser.add_argument("--wind", type=Path, required=True)
    parser.add_argument("--contact-email", default=None)
    parser.add_argument("--ack-timeout-s", type=int, default=DEMO_HOUSEHOLD.ack_timeout_s)
    parser.add_argument("--timeout-s", type=float, default=180)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if not args.confirm:
        raise SystemExit("refusing without --confirm")
    rfw, wind = args.rfw.expanduser(), args.wind.expanduser()
    check_alert(rfw, FIRE_EVENTS)
    check_alert(wind, WIND_EVENTS)

    resource: Any = boto3.resource("dynamodb")
    print(f"reset: deleted {delete_derived(resource.Table(args.table))} items")
    store, bus = Store(args.table), Bus(args.bus)
    print("seed:  " + seed(store, args.contact_email or None, args.ack_timeout_s))

    print("replay:", json.dumps(replay(rfw, store, bus, DEMO_HOUSEHOLD.id, datetime.now(UTC))))
    wait_for(store, lambda a: len(a) == 1, "the Red Flag Warning incident", args.timeout_s)
    print("replay:", json.dumps(replay(wind, store, bus, DEMO_HOUSEHOLD.id, datetime.now(UTC))))
    active = wait_for(
        store,
        lambda a: len(a) == 1 and is_ready(a[0]),
        "one triaged Fire risk incident",
        args.timeout_s,
    )
    inc, tz = active[0], DEMO_HOUSEHOLD.tz
    due = inc.escalation_due_at or ""
    print(f"\nincident    {inc.id}  ({inc.title}, {inc.severity}, {inc.status})")
    print(f"replay      {inc.replay} (originally issued {inc.replay_original_time})")
    print(f"escalation  due {local(due, tz)} ({due}); acknowledge before then")
    print(f"evidence    {[e.detail for e in inc.evidence[:2]]}")
    s = inc.summarizer
    print(f"triage      model={s.model} fallback_used={s.fallback_used}")


if __name__ == "__main__":
    main()
