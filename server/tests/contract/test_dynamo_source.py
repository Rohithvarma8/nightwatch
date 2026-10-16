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
from nightwatch_core.models import Evidence, Incident, Summarizer

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
        t.put_item(Item={"PK": "HH#hh_demo", "SK": "PROFILE", "name": "Demo Household"})
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
    assert [i["id"] for i in sc["incidents"]] == ["inc_rfw", "inc_rp", "inc_wind"]
    replayed = sc["incidents"][1]
    assert replayed["replay"] is True and replayed["replay_original_time"] is not None
    assert sc["incidents"][0]["top_action"] == "Act on Red Flag Warning"
    assert sc["incidents"][0]["evidence_preview"] == [
        "NWS Red Flag Warning, Southeastern Ventura County Valleys"
    ]
    text = result.content[0]
    assert text.type == "text" and "Heat Advisory" not in text.text and "inc_" not in text.text


async def test_no_incidents_is_all_clear(table) -> None:
    async with connect() as client:
        result = await client.call_tool("get_active_incidents", {})
    assert result.structured_content is not None
    assert result.structured_content["incidents"] == []
    assert result.content[0].type == "text"
    assert result.content[0].text == "All clear. No active incidents right now."


async def test_tool_handler_under_50ms(table) -> None:
    _put(table, _incident("inc_rfw", "Red Flag Warning", "high", ends_in=timedelta(days=2)))
    async with connect() as client:
        await client.call_tool("get_active_incidents", {})  # warm-up (name cache, connections)
        times = []
        for _ in range(5):
            start = time.perf_counter()
            await client.call_tool("get_active_incidents", {})
            times.append((time.perf_counter() - start) * 1000)
    assert sorted(times)[len(times) // 2] < 50, times
