"""get_active_incidents reading GSI1 from a moto DynamoDB table, over the real MCP transport."""

import json
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import boto3
import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from moto import mock_aws

from nightwatch.app import MCP_PATH, create_app
from nightwatch_core import keys
from nightwatch_core.models import Evidence, Incident, SignalRef, Summarizer

pytestmark = pytest.mark.anyio

TABLE = "nightwatch-test"
BASE_URL = "http://127.0.0.1:8080"
NOW = datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _incident(iid: str, title: str, severity, *, ends_in: timedelta, replay=False) -> Incident:
    return Incident(
        id=iid,
        household_id="hh_demo",
        kind="hazard",
        title=title,
        severity=severity,
        status="open",
        started_at=_iso(NOW - timedelta(hours=1)),
        updated_at=_iso(NOW),
        ends_at=_iso(NOW + ends_in),
        correlation_key=f"hh_demo#{title}#CAZ374",
        signals=[
            SignalRef(
                source="nws",
                external_id=f"{iid}.1",
                observed_at=_iso(NOW - timedelta(hours=1)),
                summary=title,
                url="https://api.weather.gov/x",
                event=title,
                hazard_family="wind" if "Wind" in title else "fire_weather",
                message_type="Alert",
                certainty="Likely",
            )
        ],
        evidence=[
            Evidence(
                type="nws_alert",
                detail=f"NWS {title}, Southeastern Ventura County Valleys",
                weight=1.0,
            )
        ],
        spoken_summary=f"The National Weather Service has a {title}.",
        detail_summary=title,
        recommended_actions=[f"Act on {title}"],
        replay=replay,
        replay_original_time=_iso(NOW - timedelta(days=1)) if replay else None,
        summarizer=Summarizer(model="template-v1", latency_ms=0, fallback_used=False),
    )


def _put(table, inc: Incident) -> None:
    """Same item layout the pipeline's incident builder writes (DESIGN.md §3)."""
    table.put_item(
        Item={
            "PK": keys.incident_pk(inc.id),
            "SK": keys.META,
            "GSI1PK": keys.active_gsi1_pk(inc.household_id),
            "GSI1SK": keys.active_gsi1_sk(inc.severity, inc.started_at),
            **json.loads(inc.model_dump_json(), parse_float=Decimal),
        }
    )


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("NIGHTWATCH_TABLE", TABLE)
    monkeypatch.setenv("HOUSEHOLD_ID", "hh_demo")
    with mock_aws():
        ddb: Any = boto3.resource("dynamodb")
        t = ddb.create_table(
            TableName=TABLE,
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
        t.put_item(
            Item={"PK": "HH#hh_demo", "SK": "PROFILE", "name": "Demo Household",
                  "tz": "America/Los_Angeles"}
        )  # fmt: skip
        t.put_item(
            Item={"PK": "HH#hh_demo", "SK": "CONTACT#c_priya", "id": "c_priya",
                  "household_id": "hh_demo", "name": "Priya", "aliases": ["roommate"],
                  "channels": {"ntfy": True, "email": "priya@example.com"},
                  "escalation_order": 1}
        )  # fmt: skip
        t.put_item(
            Item={"PK": "HH#hh_demo", "SK": "POLICY#escalation", "household_id": "hh_demo",
                  "min_severity": "high", "contact_ids": ["c_priya"]}
        )  # fmt: skip
        topic = boto3.client("sns").create_topic(Name="nightwatch-notify")["TopicArn"]
        monkeypatch.setenv("NOTIFY_TOPIC_ARN", topic)
        yield t


@asynccontextmanager
async def connect() -> AsyncIterator[Client]:
    mcp_app, asgi = create_app()
    async with (
        mcp_app.router.lifespan_context(mcp_app),
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=asgi), base_url=BASE_URL) as http,
    ):
        transport = streamable_http_client(
            f"{BASE_URL}{MCP_PATH}", http_client=http, terminate_on_close=False
        )
        async with Client(transport, mode="legacy") as client:
            yield client


async def test_reads_active_incidents_from_gsi1(table) -> None:
    _put(table, _incident("inc_wind", "Wind Advisory", "moderate", ends_in=timedelta(hours=5)))
    _put(table, _incident("inc_rfw", "Red Flag Warning", "high", ends_in=timedelta(days=2)))
    _put(
        table,
        _incident("inc_rp", "Red Flag Warning", "high", ends_in=timedelta(days=2), replay=True),
    )
    # Ended but not yet swept: must not be read out.
    _put(table, _incident("inc_old", "Heat Advisory", "low", ends_in=timedelta(minutes=-5)))
    async with connect() as client:
        result = await client.call_tool("get_active_incidents", {})

    assert not result.is_error
    sc = result.structured_content
    assert sc is not None
    assert sc["household"] == "Demo Household"
    # The replayed red flag warning is hidden: a live fire-weather incident exists.
    assert [i["id"] for i in sc["incidents"]] == ["inc_rfw", "inc_wind"]
    assert sc["incidents"][0]["top_action"] == "Act on Red Flag Warning"
    assert sc["incidents"][0]["evidence_preview"] == [
        "NWS Red Flag Warning, Southeastern Ventura County Valleys"
    ]
    text = result.content[0]
    assert text.type == "text" and "Heat Advisory" not in text.text and "inc_" not in text.text


async def test_replay_shown_when_only_data(table) -> None:
    _put(
        table,
        _incident("inc_rp", "Red Flag Warning", "high", ends_in=timedelta(days=2), replay=True),
    )
    async with connect() as client:
        result = await client.call_tool("get_active_incidents", {})
    sc = result.structured_content
    assert sc is not None
    (only,) = sc["incidents"]
    assert only["replay"] is True and only["replay_original_time"] is not None
    assert result.content[0].type == "text"
    assert result.content[0].text.startswith("One thing. 1. Replayed alert: Red Flag Warning")


async def test_explain_and_runbook_read_the_table(table) -> None:
    _put(table, _incident("inc_rfw", "Red Flag Warning", "high", ends_in=timedelta(days=2)))
    _put(table, _incident("inc_wind", "Wind Advisory", "moderate", ends_in=timedelta(hours=5)))
    async with connect() as client:
        exp = await client.call_tool("explain_incident", {"reference": "the wind thing"})
        book = await client.call_tool("get_runbook", {"incident_id": "inc_wind"})
    assert exp.structured_content is not None and exp.structured_content["id"] == "inc_wind"
    assert book.structured_content is not None
    assert book.structured_content["runbook_id"] == "wind-advisory"


async def test_no_incidents_is_all_clear(table) -> None:
    async with connect() as client:
        result = await client.call_tool("get_active_incidents", {})
    assert result.structured_content is not None
    assert result.structured_content["incidents"] == []
    assert result.content[0].type == "text"
    assert result.content[0].text == "All clear. No active incidents right now."


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("get_active_incidents", {}),
        ("explain_incident", {"reference": "the fire one"}),
        ("get_runbook", {}),
    ],
)
async def test_tool_handler_under_50ms(table, tool, args) -> None:
    _put(table, _incident("inc_rfw", "Red Flag Warning", "high", ends_in=timedelta(days=2)))
    async with connect() as client:
        await client.call_tool(tool, args)  # warm-up (name cache, connections)
        times = []
        for _ in range(5):
            start = time.perf_counter()
            result = await client.call_tool(tool, args)
            times.append((time.perf_counter() - start) * 1000)
            assert not result.is_error
    assert sorted(times)[len(times) // 2] < 50, times


def _events(table, iid: str) -> list[str]:
    items = table.query(
        KeyConditionExpression="PK = :p AND begins_with(SK, :e)",
        ExpressionAttributeValues={":p": f"INC#{iid}", ":e": "EVT#"},
    )["Items"]
    return sorted(i["type"] for i in items)


async def test_acknowledge_writes_status_and_timeline(table) -> None:
    _put(table, _incident("inc_rfw", "Red Flag Warning", "high", ends_in=timedelta(days=2)))
    async with connect() as client:
        result = await client.call_tool("acknowledge", {"incident_id": "inc_rfw"})
    assert not result.is_error
    item = table.get_item(Key={"PK": "INC#inc_rfw", "SK": "META"})["Item"]
    assert item["status"] == "acknowledged" and item["acked_at"] and item["version"] == 1
    assert item["GSI1PK"] == "HH#hh_demo#ACTIVE"  # still active, still listed
    assert _events(table, "inc_rfw") == ["acknowledged"]


async def test_notify_contact_publishes_and_rate_limits(table) -> None:
    _put(table, _incident("inc_rfw", "Red Flag Warning", "high", ends_in=timedelta(days=2)))
    async with connect() as client:
        results = [
            await client.call_tool("notify_contact", {"contact": "roommate"}) for _ in range(4)
        ]
    assert [r.is_error for r in results] == [False, False, False, True]
    assert _events(table, "inc_rfw") == ["notified"] * 3
    rate = table.query(
        KeyConditionExpression="PK = :p", ExpressionAttributeValues={":p": "RATE#hh_demo#c_priya"}
    )["Items"]
    assert len(rate) == 1 and rate[0]["count"] == 3 and rate[0]["expires_at"]


async def test_escalate_sets_status_and_publishes(table) -> None:
    _put(table, _incident("inc_rfw", "Red Flag Warning", "high", ends_in=timedelta(days=2)))
    async with connect() as client:
        result = await client.call_tool("escalate", {})
    assert result.structured_content is not None
    assert result.structured_content["escalated_to"] == "Priya (roommate)"
    item = table.get_item(Key={"PK": "INC#inc_rfw", "SK": "META"})["Item"]
    assert item["status"] == "escalated"
    assert _events(table, "inc_rfw") == ["escalated"]


async def test_sns_failure_is_a_clear_tool_error(table, monkeypatch) -> None:
    _put(table, _incident("inc_rfw", "Red Flag Warning", "high", ends_in=timedelta(days=2)))
    monkeypatch.setenv("NOTIFY_TOPIC_ARN", "arn:aws:sns:us-west-2:123456789012:does-not-exist")
    async with connect() as client:
        result = await client.call_tool("notify_contact", {"contact": "Priya"})
    assert result.is_error and result.content[0].type == "text"
    assert result.content[0].text == (
        "I couldn't reach the notification service, so Priya wasn't notified. "
        "Please try again in a minute."
    )
    assert _events(table, "inc_rfw") == []


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("acknowledge", {}),
        ("notify_contact", {"contact": "roommate"}),
        ("escalate", {}),
    ],
)
async def test_action_handlers_under_50ms(table, tool, args) -> None:
    _put(table, _incident("inc_rfw", "Red Flag Warning", "high", ends_in=timedelta(days=2)))
    async with connect() as client:
        await client.call_tool("get_active_incidents", {})  # warm caches
        start = time.perf_counter()
        result = await client.call_tool(tool, args)
        elapsed = (time.perf_counter() - start) * 1000
    assert not result.is_error and elapsed < 50, elapsed
