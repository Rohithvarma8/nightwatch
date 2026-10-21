"""Night Watch MCP server entry point: `uvicorn nightwatch.app:asgi`."""

from mcp.server.apps import Apps
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from nightwatch import settings as settings_mod
from nightwatch.domain.fixtures import FixtureNotifier, FixtureSource
from nightwatch.domain.incidents import IncidentSource, Notifier
from nightwatch.domain.runbooks import load_runbooks
from nightwatch.tools import actions, card, explain, incidents, rollback, runbooks

MCP_PATH = "/mcp"
# The SDK's defaults when host="127.0.0.1"; kept so `make run` and the Inspector keep working.
LOCAL_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
LOCAL_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]


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


def incident_source(cfg: settings_mod.Settings) -> IncidentSource:
    if cfg.table_name is None:
        return FixtureSource()
    from nightwatch.store.incidents import DynamoIncidentSource  # boto3 only when configured

    return DynamoIncidentSource(cfg.table_name, cfg.household_id)


def notifier_for(cfg: settings_mod.Settings) -> Notifier:
    if not cfg.notify_topic_arn:
        return FixtureNotifier()  # local dev / tests: nothing leaves the process
    from nightwatch.store.notify import SnsNotifier

    return SnsNotifier(cfg.notify_topic_arn)


def deployer_for(cfg: settings_mod.Settings) -> rollback.Deployer | None:
    if not (cfg.codedeploy_app and cfg.codedeploy_group):
        return None
    from nightwatch.store.deploys import CodeDeployRollback

    return CodeDeployRollback(cfg.codedeploy_app, cfg.codedeploy_group)


def create_server(
    source: IncidentSource, notifier: Notifier, deployer: rollback.Deployer | None = None
) -> MCPServer:
    # MCP Apps: the three read tools carry _meta.ui.resourceUri → the incident card. Extensions
    # are applied at construction, so the Apps tools are bound before the server exists.
    apps = Apps()
    books = load_runbooks()  # read once at init, no per-request I/O
    card.register(apps)  # HTML read once at init, no per-request I/O
    incidents.register(apps, source, books)
    explain.register(apps, source, books)
    runbooks.register(apps, source, books)
    server = MCPServer(
        name="nightwatch",
        title="Night Watch",
        version="0.1.0",
        instructions="Household incident commander: home hazards and production on-call alerts.",
        extensions=[apps],
    )
    actions.register(server, source, notifier)
    rollback.register(server, source, deployer)
    server.custom_route("/healthz", methods=["GET"], include_in_schema=False)(healthz)
    return server


def transport_security(allowed_hosts: str) -> TransportSecuritySettings:
    """DNS-rebinding protection: localhost plus comma-separated public hosts.

    The SDK's default allows only localhost, so behind API Gateway every request would get
    421 Invalid Host header. Terraform sets MCP_ALLOWED_HOSTS to the execute-api domain.
    """
    hosts = [h.strip() for h in allowed_hosts.split(",") if h.strip()]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=LOCAL_HOSTS + hosts,
        allowed_origins=LOCAL_ORIGINS + [f"https://{h}" for h in hosts],
    )


def create_app() -> tuple[Starlette, ASGIApp]:
    """Return (mcp_app, asgi). mcp_app owns the lifespan; asgi is what uvicorn serves."""
    cfg = settings_mod.load()
    server = create_server(incident_source(cfg), notifier_for(cfg), deployer_for(cfg))
    mcp_app = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        json_response=True,
        transport_security=transport_security(cfg.allowed_hosts),
    )
    return mcp_app, RejectGetStream(mcp_app)


mcp_app, asgi = create_app()
