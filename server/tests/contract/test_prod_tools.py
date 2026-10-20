"""Prod incidents through the existing tools, the replayed wording, and rollback_deploy."""

import json
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

from nightwatch import settings as settings_mod
from nightwatch.app import MCP_PATH, create_server, transport_security
from nightwatch.domain.fixtures import FixtureNotifier
from nightwatch.store.incidents import DynamoIncidentSource
from nightwatch_core import keys
from nightwatch_core.models import Evidence, Incident, SignalRef, Summarizer

pytestmark = pytest.mark.anyio
TABLE = "nightwatch-test"
NOW = datetime.now(UTC)
ISO = "%Y-%m-%dT%H:%M:%SZ"


def _prod_incident(*, replay: bool = False, deploy_id: str | None = "d-ABC123") -> Incident:
    refs = [
        SignalRef(
            source="cloudwatch",
            external_id="alarm#1",
            observed_at=NOW.strftime(ISO),
            summary="nightwatch-checkout-latency-p95 is ALARM",
            url="https://x",
            event="checkout-service latency",
            hazard_family="prod",
            message_type="Alert",
            certainty="Observed",
        )
    ]
    evidence = [Evidence(type="alarm", detail="nightwatch-checkout-latency-p95 in ALARM", weight=1)]
    if deploy_id:
        refs.append(
            SignalRef(
                source="codedeploy",
                external_id=deploy_id,
                observed_at=(NOW - timedelta(minutes=4)).strftime(ISO),
                summary="Deployment",
                url="https://y",
                event="Deployment",
                hazard_family="prod",
                role="supporting",
            )
        )
        evidence.append(
            Evidence(
                type="deploy_proximity",
                detail=f"Latency rose 4 minutes after deployment {deploy_id} (v3→v4); no other "
                "service changed",
                spoken="Latency rose 4 minutes after a deploy from version 3 to 4",
                weight=0.8,
            )
        )
    return Incident(
        id="inc_prod",
        household_id="hh_demo",
        kind="prod",
        title="checkout-service latency",
        severity="high",
        status="open",
        started_at=NOW.strftime(ISO),
        updated_at=NOW.strftime(ISO),
        ends_at=(NOW + timedelta(days=7)).strftime(ISO),
        correlation_key="hh_demo#prod#checkout-service",
        signals=refs,
        evidence=evidence,
        area_name="checkout-service",
        replay=replay,
        spoken_summary="checkout-service latency rose above its alarm threshold 4 minutes after "
        "a deploy from version 3 to 4.",
        detail_summary="Alarm.",
        recommended_actions=["Roll back the latest deploy"],
        summarizer=Summarizer(model="template-v1", latency_ms=0, fallback_used=False),
    )


def _put(table: Any, inc: Incident) -> None:
    table.put_item(
        Item={
            "PK": keys.incident_pk(inc.id),
            "SK": keys.META,
            "GSI1PK": keys.active_gsi1_pk(inc.household_id),
            "GSI1SK": keys.active_gsi1_sk(inc.severity, inc.started_at),
            **json.loads(inc.model_dump_json(), parse_float=Decimal),
        }
    )


def _deploy(table: Any, deployment_id: str, frm: str, to: str, minutes_ago: int) -> None:
    ended = (NOW - timedelta(minutes=minutes_ago)).strftime(ISO)
    table.put_item(
        Item={
            "PK": "SVC#checkout-service",
            "SK": f"DEPLOY#{ended}#{deployment_id}",
            "service": "checkout-service",
            "deployment_id": deployment_id,
            "from_version": frm,
            "to_version": to,
            "ended_at": ended,
        }
    )


class FakeDeployer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def start(self, function: str, current: str, target: str) -> str:
        self.calls.append((function, current, target))
        return "d-ROLLBACK1"


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    for k, v in {
        "AWS_DEFAULT_REGION": "us-west-2",
        "AWS_ACCESS_KEY_ID": "t",
        "AWS_SECRET_ACCESS_KEY": "t",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
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
            Item={
                "PK": "HH#hh_demo",
                "SK": "PROFILE",
                "name": "Demo Household",
                "tz": "America/Los_Angeles",
            }
        )
        yield t


@asynccontextmanager
async def connect(deployer: FakeDeployer | None) -> AsyncIterator[Client]:
    server = create_server(DynamoIncidentSource(TABLE, "hh_demo"), FixtureNotifier(), deployer)
    app = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        json_response=True,
        transport_security=transport_security(settings_mod.load().allowed_hosts),
    )
    base = "http://127.0.0.1:8080"
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=base) as http,
    ):
        transport = streamable_http_client(
            f"{base}{MCP_PATH}", http_client=http, terminate_on_close=False
        )
        async with Client(transport, mode="legacy") as client:
            yield client


async def test_prod_incident_through_existing_tools(table) -> None:
    _put(table, _prod_incident())
    async with connect(None) as client:
        work = await client.call_tool("get_active_incidents", {"scope": "work"})
        home = await client.call_tool("get_active_incidents", {"scope": "home"})
        exp = await client.call_tool("explain_incident", {"reference": "the checkout alarm"})
        book = await client.call_tool("get_runbook", {"reference": "the checkout alarm"})
    assert work.structured_content is not None and home.structured_content is not None
    assert [i["title"] for i in work.structured_content["incidents"]] == [
        "checkout-service latency"
    ]
    assert home.structured_content["incidents"] == []
    assert exp.structured_content is not None
    assert exp.structured_content["what_it_means_for_you"].startswith("Customers may be seeing")
    assert exp.content[0].type == "text"
    spoken = exp.content[0].text
    assert "Latency rose 4 minutes after a deploy from version 3 to 4" in spoken
    assert "d-ABC123" not in spoken  # never read IDs aloud
    assert any("d-ABC123" in e["detail"] for e in exp.structured_content["evidence"])
    assert book.structured_content is not None
    assert book.structured_content["runbook_id"] == "deploy-regression"


async def test_replayed_wording_mid_sentence(table) -> None:
    _put(
        table,
        _prod_incident(replay=True, deploy_id=None).model_copy(
            update={"kind": "hazard", "title": "Red Flag Warning"}
        ),
    )
    async with connect(None) as client:
        result = await client.call_tool("acknowledge", {})
    assert result.content[0].type == "text"
    assert result.content[0].text == "Got it. I've acknowledged the replayed Red Flag Warning."


async def test_rollback_requires_confirm(table) -> None:
    _put(table, _prod_incident())
    _deploy(table, "d-ABC123", "3", "4", 4)
    deployer = FakeDeployer()
    async with connect(deployer) as client:
        result = await client.call_tool("rollback_deploy", {"confirm": False})
    assert result.is_error and deployer.calls == []
    assert result.content[0].type == "text"
    assert result.content[0].text == (
        "To roll back checkout-service from version 4 to 3, ask me again and confirm."
    )


async def test_rollback_starts_deploy_to_previous_version(table) -> None:
    _put(table, _prod_incident())
    _deploy(table, "d-OLD", "2", "3", 60)
    _deploy(table, "d-ABC123", "3", "4", 4)
    deployer = FakeDeployer()
    async with connect(deployer) as client:
        result = await client.call_tool(
            "rollback_deploy", {"confirm": True, "reference": "the checkout alarm"}
        )
    assert deployer.calls == [("checkout-service", "4", "3")]
    assert result.structured_content == {
        "deployment_id": "d-ROLLBACK1",
        "service": "checkout-service",
        "from_version": "4",
        "to_version": "3",
        "status": "started",
    }
    assert result.content[0].type == "text" and "d-ROLLBACK1" not in result.content[0].text


async def test_rollback_refuses_when_redeployed_since(table) -> None:
    _put(table, _prod_incident())
    _deploy(table, "d-ABC123", "3", "4", 4)
    _deploy(table, "d-NEWER", "4", "5", 1)  # someone deployed again (e.g. already rolled back)
    deployer = FakeDeployer()
    async with connect(deployer) as client:
        result = await client.call_tool("rollback_deploy", {"confirm": True})
    assert result.is_error and deployer.calls == []
    assert result.content[0].type == "text"
    assert "deployed again since this alarm started" in result.content[0].text


async def test_rollback_refuses_without_linked_deploy(table) -> None:
    _put(table, _prod_incident(deploy_id=None))
    deployer = FakeDeployer()
    async with connect(deployer) as client:
        result = await client.call_tool("rollback_deploy", {"confirm": True})
    assert result.is_error and deployer.calls == []
