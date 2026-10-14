from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from starlette.applications import Starlette
from starlette.types import ASGIApp

from nightwatch.app import MCP_PATH, create_app

BASE_URL = "http://127.0.0.1:8080"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def app() -> AsyncIterator[tuple[Starlette, ASGIApp]]:
    """Fresh in-process app with its lifespan (session manager) running."""
    mcp_app, asgi = create_app()
    async with mcp_app.router.lifespan_context(mcp_app):
        yield mcp_app, asgi


@pytest.fixture
async def http(app: tuple[Starlette, ASGIApp]) -> AsyncIterator[httpx2.AsyncClient]:
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app[1]), base_url=BASE_URL
    ) as client:
        yield client


@pytest.fixture
def mcp_client(
    http: httpx2.AsyncClient,
) -> Callable[[], AbstractAsyncContextManager[Client]]:
    """SDK client over Streamable HTTP against the in-process ASGI app (initialize handshake)."""

    @asynccontextmanager
    async def connect() -> AsyncIterator[Client]:
        transport = streamable_http_client(
            f"{BASE_URL}{MCP_PATH}", http_client=http, terminate_on_close=False
        )
        async with Client(transport, mode="legacy") as client:
            yield client

    return connect
