"""MCP Apps: the incident card resource is listed, served as an MCP App, and bound to tools."""

import re
from typing import Any

import httpx2
import pytest
from mcp.server.apps import APP_MIME_TYPE

from nightwatch.app import MCP_PATH
from nightwatch.tools.card import CARD_URI, card_html

from .test_transport import JSON_HEADERS, ClientFactory

pytestmark = pytest.mark.anyio

CARD_TOOLS = {"get_active_incidents", "explain_incident", "get_runbook"}


async def test_card_resource_is_listed_as_mcp_app(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        resources = (await client.list_resources()).resources
    (card,) = [r for r in resources if r.uri == CARD_URI]
    assert card.mime_type == APP_MIME_TYPE == "text/html;profile=mcp-app"


async def test_card_resource_is_served(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        result = await client.read_resource(CARD_URI)
    (content,) = result.contents
    assert str(content.uri) == CARD_URI
    assert content.mime_type == APP_MIME_TYPE
    text = getattr(content, "text", "")
    assert text.startswith("<!doctype html>") and "ui/initialize" in text
    assert text == card_html()


async def test_only_the_read_tools_reference_the_card(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        tools = (await client.list_tools()).tools
    bound = {t.name for t in tools if (t.meta or {}).get("ui", {}).get("resourceUri") == CARD_URI}
    assert bound == CARD_TOOLS
    assert all("ui" not in (t.meta or {}) for t in tools if t.name not in CARD_TOOLS)


@pytest.mark.parametrize("version", ["2025-03-26", "2025-11-25"])
async def test_card_reaches_pre_2026_clients(http: httpx2.AsyncClient, version: str) -> None:
    # The SDK only advertises capabilities.extensions on the 2026-07-28 wire (FL-012), so for
    # the versions Alexa+ sends, hosts discover the card from tool _meta.ui.resourceUri.
    headers = {**JSON_HEADERS, "MCP-Protocol-Version": version}

    async def rpc(method: str, params: dict[str, object]) -> dict[str, Any]:
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        resp = await http.post(MCP_PATH, json=body, headers=headers)
        assert resp.status_code == 200
        return resp.json()["result"]

    tools = (await rpc("tools/list", {}))["tools"]
    bound = {t["name"] for t in tools if t.get("_meta", {}).get("ui", {}).get("resourceUri")}
    assert bound == CARD_TOOLS
    listed = (await rpc("resources/list", {}))["resources"]
    assert {"uri": CARD_URI, "mimeType": APP_MIME_TYPE}.items() <= next(
        r for r in listed if r["uri"] == CARD_URI
    ).items()
    (content,) = (await rpc("resources/read", {"uri": CARD_URI}))["contents"]
    assert content["mimeType"] == APP_MIME_TYPE and content["text"] == card_html()


def test_card_html_makes_no_external_requests() -> None:
    html = card_html()
    url = r"https?:|wss?:|//[\w.-]+\.\w"  # absolute or protocol-relative
    assert not re.search(url, html, re.I)
    assert not re.search(r"<(link|img|iframe|object|embed|base)\b", html, re.I)
    assert not re.search(r"<script[^>]*\bsrc=", html, re.I)
    assert not re.search(r"@import|url\(|@font-face", html, re.I)
    assert not re.search(r"\b(fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon)\b", html)


def test_card_html_never_injects_markup() -> None:
    # Incident text comes from alert feeds; it must only ever reach the DOM as text.
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", card_html())


async def test_text_stays_complete_without_the_card(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:  # the SDK client doesn't negotiate Apps
        overview = await client.call_tool("get_active_incidents", {})
        why = await client.call_tool("explain_incident", {"reference": "checkout"})
    text = overview.content[0]
    assert text.type == "text"
    assert "Red Flag Warning" in text.text and "checkout" in text.text.lower()
    assert why.content[0].type == "text" and "version 42 to 43" in why.content[0].text
    assert why.structured_content is not None
    view = why.structured_content["incident"]
    assert view["deploy_versions"] == "v42→v43" and view["severity"] and view["status"]


async def test_every_card_result_has_the_same_header(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        results = [
            await client.call_tool("get_active_incidents", {}),
            await client.call_tool("explain_incident", {"reference": "fire"}),
            await client.call_tool("get_runbook", {"reference": "fire"}),
        ]
    for result in results:
        sc = result.structured_content
        assert sc is not None and sc["household"] == "Demo Household"
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", sc["as_of"])
    steps = results[2].structured_content["steps"]  # type: ignore[index]
    assert steps[0]["n"] == 1 and all(not s["done"] for s in steps)
