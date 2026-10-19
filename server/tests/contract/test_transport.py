"""Contract tests: SDK client <-> in-process app over Streamable HTTP."""

import json
import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path

import httpx2
import mcp.client.session
import pytest
from mcp import Client

from nightwatch.app import MCP_PATH

pytestmark = pytest.mark.anyio

ClientFactory = Callable[[], AbstractAsyncContextManager[Client]]
SNAPSHOT = Path(__file__).parent.parent / "__snapshots__" / "tools_list.json"
JSON_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.mark.parametrize("version", ["2025-03-26", "2025-11-25"])
async def test_initialize_negotiates_requested_version(
    mcp_client: ClientFactory, monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    # The SDK client always offers its latest handshake version; pin it to what Alexa+ sends.
    monkeypatch.setattr(mcp.client.session, "LATEST_HANDSHAKE_VERSION", version)
    async with mcp_client() as client:
        init = client.session.initialize_result
        assert init is not None
        assert init.protocol_version == version
        assert init.server_info.name == "nightwatch"
        assert init.capabilities.tools is not None


@pytest.mark.parametrize("version", ["2025-03-26", "2025-11-25"])
async def test_raw_initialize_returns_json(http: httpx2.AsyncClient, version: str) -> None:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": version,
            "capabilities": {},
            "clientInfo": {"name": "alexa-plus", "version": "1.0"},
        },
    }
    resp = await http.post(MCP_PATH, json=body, headers=JSON_HEADERS)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["result"]["protocolVersion"] == version


async def test_tools_list_matches_snapshot(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        tools = (await client.list_tools()).tools
    actual = [t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in tools]
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
    # Schema changes must be deliberate: update the snapshot AND run `alexa-ai deploy`.
    assert actual == json.loads(SNAPSHOT.read_text())


async def test_get_active_incidents_is_read_only(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        (tool,) = [t for t in (await client.list_tools()).tools if t.name == "get_active_incidents"]
    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is True
    assert tool.output_schema is not None


async def test_call_get_active_incidents(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        result = await client.call_tool("get_active_incidents", {})
    assert not result.is_error
    text = result.content[0]
    assert text.type == "text"
    assert "Red Flag Warning" in text.text and "inc_" not in text.text

    sc = result.structured_content
    assert sc is not None
    assert sc["household"] == "Demo Household"
    assert [i["title"] for i in sc["incidents"]] == ["Red Flag Warning", "checkout-service latency"]
    assert {i["kind"] for i in sc["incidents"]} == {"hazard", "prod"}
    for inc in sc["incidents"]:
        assert len(inc["spoken_summary"].split()) <= 40
        assert inc["replay"] is False


async def test_call_scope_filter(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        result = await client.call_tool("get_active_incidents", {"scope": "work"})
    assert result.structured_content is not None
    assert [i["kind"] for i in result.structured_content["incidents"]] == ["prod"]


async def test_call_rejects_bad_limit(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        result = await client.call_tool("get_active_incidents", {"limit": 99})
    assert result.is_error


async def test_get_mcp_is_405(http: httpx2.AsyncClient) -> None:
    resp = await http.get(MCP_PATH, headers={"Accept": "text/event-stream"})
    assert resp.status_code == 405


async def test_healthz(http: httpx2.AsyncClient) -> None:
    resp = await http.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_explain_defaults_to_top_incident(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        result = await client.call_tool("explain_incident", {})
    assert not result.is_error
    sc = result.structured_content
    assert sc is not None and sc["title"] == "Red Flag Warning"
    assert {"what_happened", "what_it_means_for_you", "evidence", "confidence", "timeline",
            "sources"} <= set(sc)  # fmt: skip
    assert result.content[0].type == "text" and "inc_" not in result.content[0].text


async def test_explain_by_reference(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        result = await client.call_tool("explain_incident", {"reference": "the deploy thing"})
    assert result.structured_content is not None
    assert result.structured_content["title"] == "checkout-service latency"


async def test_explain_no_match_is_tool_error(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        result = await client.call_tool("explain_incident", {"reference": "the flood one"})
    assert result.is_error
    text = result.content[0]
    assert text.type == "text"
    assert text.text == (
        "I couldn't find an incident matching 'the flood one'. "
        "Active right now: Red Flag Warning; checkout-service latency."
    )


async def test_get_runbook(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        result = await client.call_tool("get_runbook", {"reference": "checkout"})
    sc = result.structured_content
    assert sc is not None and sc["runbook_id"] == "deploy-regression"
    assert sc["next_step"] == sc["steps"][0]["action"]
    assert all(s["why"] and s["done"] is False for s in sc["steps"])
    assert result.content[0].type == "text"
    assert result.content[0].text.startswith("For the checkout-service latency: first,")


async def test_three_tools_listed(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        tools = (await client.list_tools()).tools
    assert sorted(t.name for t in tools) == [
        "explain_incident",
        "get_active_incidents",
        "get_runbook",
    ]
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)
