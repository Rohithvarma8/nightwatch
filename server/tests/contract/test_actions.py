"""acknowledge / notify_contact / escalate over the real MCP transport (fixture source)."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pytest
from mcp import Client

pytestmark = pytest.mark.anyio
ClientFactory = Callable[[], AbstractAsyncContextManager[Client]]


async def test_acknowledge_is_idempotent_and_cancels_escalation(mcp_client: ClientFactory):
    async with mcp_client() as client:
        first = await client.call_tool("acknowledge", {"reference": "the fire one"})
        second = await client.call_tool("acknowledge", {"reference": "the fire one"})
    assert first.structured_content is not None and second.structured_content is not None
    sc = first.structured_content
    assert sc["status"] == "acknowledged" and sc["acked_at"] and sc["escalation_cancelled"] is True
    assert first.content[0].type == "text"
    assert first.content[0].text == (
        "Got it. I've acknowledged the Red Flag Warning, so the escalation is cancelled."
    )
    assert second.structured_content["acked_at"] == sc["acked_at"]
    assert second.structured_content["escalation_cancelled"] is False
    assert second.content[0].type == "text"
    assert second.content[0].text == "The Red Flag Warning was already acknowledged."


async def test_overview_shows_acknowledged(mcp_client: ClientFactory):
    async with mcp_client() as client:
        await client.call_tool("acknowledge", {})
        result = await client.call_tool("get_active_incidents", {})
    assert result.content[0].type == "text"
    assert "1. Red Flag Warning, high, acknowledged:" in result.content[0].text
    assert result.structured_content is not None
    assert result.structured_content["incidents"][0]["escalation_due_at"] is None


@pytest.mark.parametrize("who", ["roommate", "my roommate", "Priya", "priya"])
async def test_notify_contact_resolves_name_or_alias(mcp_client: ClientFactory, who: str):
    async with mcp_client() as client:
        result = await client.call_tool("notify_contact", {"contact": who})
    assert not result.is_error
    sc = result.structured_content
    assert sc is not None
    assert sc["queued"] is True and sc["contact"] == "Priya" and sc["relationship"] == "roommate"
    assert sc["channels"] == ["push", "email"]
    assert sc["message_preview"] == (
        "Red Flag Warning for Southeastern Ventura County Valleys until 4 PM December 31. "
        "Keep windows closed. —Night Watch"
    )
    assert result.content[0].type == "text"
    assert result.content[0].text == (
        "Done. I sent Priya a push notification and an email about the Red Flag Warning."
    )


async def test_notify_unknown_contact_lists_known(mcp_client: ClientFactory):
    async with mcp_client() as client:
        result = await client.call_tool("notify_contact", {"contact": "mom"})
    assert result.is_error and result.content[0].type == "text"
    assert result.content[0].text == (
        "I couldn't find a contact called 'mom'. Your contacts: Priya (roommate)."
    )


async def test_notify_rate_limit_three_per_hour(mcp_client: ClientFactory):
    async with mcp_client() as client:
        results = [
            await client.call_tool("notify_contact", {"contact": "roommate"}) for _ in range(4)
        ]
    assert [r.is_error for r in results] == [False, False, False, True]
    last = results[-1].content[0]
    assert last.type == "text"
    assert last.text == (
        "I've already sent Priya 3 messages in the last hour, so I didn't send another one."
    )


async def test_escalate_notifies_first_policy_contact(mcp_client: ClientFactory):
    async with mcp_client() as client:
        result = await client.call_tool("escalate", {"reference": "checkout"})
    sc = result.structured_content
    assert sc is not None
    assert sc == {
        "id": "inc_01JZ8Q6F2C8H4W7P3S9D5G1XYB",
        "escalated_to": "Priya (roommate)",
        "channels": ["push", "email"],
        "status": "escalated",
    }
    assert result.content[0].type == "text" and "inc_" not in result.content[0].text
