import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws

from nightwatch_pipeline.bus import Bus
from nightwatch_pipeline.seed import DEMO_HOUSEHOLD
from nightwatch_pipeline.store import Store

FIXTURES = Path(__file__).parent / "fixtures" / "nws"
TABLE = "nightwatch-test"
BUS = "nightwatch-test"
# Inside the archived Red Flag Warning's window (sent Oct 15 13:16 PDT, ends Oct 17 20:00 PDT).
NOW = datetime(2026, 10, 15, 21, 0, tzinfo=UTC)


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def create_table(name: str = TABLE) -> None:
    """Same schema as infra/modules/data."""
    boto3.client("dynamodb").create_table(
        TableName=name,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": a, "AttributeType": "S"} for a in ("PK", "SK", "GSI1PK", "GSI1SK")
        ],
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )


@pytest.fixture
def aws(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(var, "testing")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    with mock_aws():
        yield


@pytest.fixture
def store(aws: None) -> Store:
    create_table()
    s = Store(TABLE)
    s.put_household(DEMO_HOUSEHOLD)
    return s


class RecordingBus(Bus):
    """Real PutEvents against moto, plus a record of what was published."""

    def __init__(self) -> None:
        boto3.client("events").create_event_bus(Name=BUS)
        super().__init__(BUS)
        self.published: list = []

    def publish(self, signals):  # type: ignore[override]
        failed = super().publish(signals)
        self.published.extend(s for s in signals if s not in failed)
        return failed


@pytest.fixture
def bus(aws: None) -> RecordingBus:
    return RecordingBus()
