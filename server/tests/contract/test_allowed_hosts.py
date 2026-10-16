"""DNS-rebinding protection: public hosts come from MCP_ALLOWED_HOSTS; localhost always works."""

import httpx2
import pytest

from nightwatch.app import MCP_PATH, create_app

pytestmark = pytest.mark.anyio

API_HOST = "abc123.execute-api.us-west-2.amazonaws.com"
JSON_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "alexa-plus", "version": "1.0"},
    },
}


async def post_initialize(base_url: str, headers: dict[str, str] | None = None) -> int:
    mcp_app, asgi = create_app()
    async with (
        mcp_app.router.lifespan_context(mcp_app),
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=asgi), base_url=base_url) as c,
    ):
        resp = await c.post(MCP_PATH, json=INITIALIZE, headers=JSON_HEADERS | (headers or {}))
    return resp.status_code


@pytest.mark.parametrize(
    ("env", "base_url", "headers", "expected"),
    [
        ("", f"https://{API_HOST}", None, 421),  # SDK default: localhost only
        (API_HOST, f"https://{API_HOST}", None, 200),
        (f" other.example.com , {API_HOST} ", f"https://{API_HOST}", None, 200),
        (API_HOST, "https://evil.example.com", None, 421),
        (API_HOST, "http://127.0.0.1:8080", None, 200),  # make run keeps working
        ("", "http://localhost:8080", None, 200),
        (API_HOST, f"https://{API_HOST}", {"Origin": f"https://{API_HOST}"}, 200),
        (API_HOST, f"https://{API_HOST}", {"Origin": "https://evil.example.com"}, 403),
    ],
)
async def test_allowed_hosts(
    monkeypatch: pytest.MonkeyPatch,
    env: str,
    base_url: str,
    headers: dict[str, str] | None,
    expected: int,
) -> None:
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", env)
    assert await post_initialize(base_url, headers) == expected
