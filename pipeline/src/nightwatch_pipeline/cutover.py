"""Day 4 cutover (dev only): delete derived data so the new rules rebuild it from live alerts.

Day 3 signal records stored only the dedupe marker, not the alert text the Day 4 rules and the
triage agent need. Deleting INC#*, OPENKEY#*, and SIG#* items (households stay) lets the next
5-minute NWS run re-ingest every active alert through the new path. Replays must be re-run.

    python -m nightwatch_pipeline.cutover --table nightwatch --confirm
"""

import argparse
from typing import Any

import boto3


def is_derived(item: dict[str, Any]) -> bool:
    pk, sk = str(item["PK"]), str(item["SK"])
    return pk.startswith(("INC#", "SIG#")) or sk.startswith("OPENKEY#")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", required=True)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if not args.confirm:
        raise SystemExit("refusing without --confirm")
    resource: Any = boto3.resource("dynamodb")
    table = resource.Table(args.table)
    scan: dict[str, Any] = {"ProjectionExpression": "PK, SK"}
    deleted = 0
    with table.batch_writer() as batch:
        while True:
            page = table.scan(**scan)
            for item in page["Items"]:
                if is_derived(item):
                    batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
                    deleted += 1
            if "LastEvaluatedKey" not in page:
                break
            scan["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    print(f"deleted {deleted} derived items from {args.table}")


if __name__ == "__main__":
    main()
