"""get_active_incidents tool."""

from datetime import UTC, datetime
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from nightwatch.domain.incidents import (
    MAX_LIMIT,
    IncidentSource,
    build_active_incidents,
    overview,
    select_active,
)
from nightwatch.domain.models import ActiveIncidents, Scope, Severity

DESCRIPTION = (
    "Use when the user asks what's going on, whether anything is wrong, or for a status "
    "overview of the household. Covers home hazards (weather warnings, air quality, nearby "
    "fires) and production on-call alerts. Returns the most severe active incidents (most recent "
    "first within a severity), each with a short spoken summary and the single most important "
    "action to take. Replayed alerts are labeled and only shown when nothing live covers them."
)


def register(server: MCPServer, source: IncidentSource) -> None:
    @server.tool(
        name="get_active_incidents",
        title="Active incidents",
        description=DESCRIPTION,
        annotations=ToolAnnotations(
            title="Active incidents",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    def get_active_incidents(
        scope: Annotated[
            Scope, Field(description="home = hazards, work = production on-call, all = both.")
        ] = "all",
        min_severity: Annotated[
            Severity, Field(description="Only return incidents at or above this severity.")
        ] = "low",
        limit: Annotated[
            int, Field(ge=1, le=MAX_LIMIT, description="Maximum incidents to return.")
        ] = 3,
    ) -> Annotated[CallToolResult, ActiveIncidents]:
        now = datetime.now(UTC)
        ranked = overview(source.active_incidents(now), now)
        selected = select_active(ranked, scope, min_severity, limit)
        as_of = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        result = build_active_incidents(selected, source.household_name(), as_of)
        return CallToolResult(
            content=[TextContent(type="text", text=result.spoken_overview)],
            structured_content=result.model_dump(mode="json"),
        )
