"""Night Watch MCP server entry point: `uvicorn nightwatch.app:asgi`."""

from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from nightwatch.tools import incidents

MCP_PATH = "/mcp"


class RejectGetStream:
    """Stateless server: no standalone SSE stream, so GET /mcp is 405."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "GET" and scope["path"] == MCP_PATH:
            response = JSONResponse(
                {"error": "Method Not Allowed"}, status_code=405, headers={"Allow": "POST"}
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


async def healthz(_: Request) -> Response:
    return JSONResponse({"status": "ok"})


def create_server() -> MCPServer:
    server = MCPServer(
        name="nightwatch",
        title="Night Watch",
        version="0.1.0",
        instructions="Household incident commander: home hazards and production on-call alerts.",
    )
    incidents.register(server)
    server.custom_route("/healthz", methods=["GET"], include_in_schema=False)(healthz)
    return server


def create_app() -> tuple[Starlette, ASGIApp]:
    """Return (mcp_app, asgi). mcp_app owns the lifespan; asgi is what uvicorn serves."""
    mcp_app = create_server().streamable_http_app(
        streamable_http_path=MCP_PATH, stateless_http=True, json_response=True
    )
    return mcp_app, RejectGetStream(mcp_app)


mcp_app, asgi = create_app()
