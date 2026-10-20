"""explain_incident tool."""

from datetime import UTC, datetime
from typing import Annotated

from mcp.server.apps import Apps
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from nightwatch.domain.explain import Depth, Explanation, explain, spoken_explanation
from nightwatch.domain.incidents import IncidentSource
from nightwatch.tools.card import CARD_URI
from nightwatch.tools.common import resolve_incident

DESCRIPTION = (
    "Use when the user asks why, how you know, what an alert means, or for more detail about an "
    "incident (for example 'why?', 'tell me more about the fire one', 'what's the wind thing'). "
    "Defaults to the top-ranked active incident. Pass `reference` with the user's own words to "
    "pick a different one. Returns what happened, what it means for the household, the evidence "
    "behind it, a confidence level, a timeline, and the sources."
)


def register(apps: Apps, source: IncidentSource) -> None:
    @apps.tool(
        resource_uri=CARD_URI,
        name="explain_incident",
        title="Explain an incident",
        description=DESCRIPTION,
        annotations=ToolAnnotations(
            title="Explain an incident",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    def explain_incident(
        incident_id: Annotated[
            str | None, Field(description="Exact incident id from a previous result, if known.")
        ] = None,
        reference: Annotated[
            str | None,
            Field(
                description="How the user referred to it, e.g. 'the fire one' or 'the wind "
                "thing'. Matched against titles, alert types, and hazard types.",
                max_length=200,
            ),
        ] = None,
        depth: Annotated[
            Depth, Field(description="brief = top evidence only; full = all evidence + timeline.")
        ] = "brief",
    ) -> Annotated[CallToolResult, Explanation]:
        now = datetime.now(UTC)
        incident = resolve_incident(source, now, incident_id, reference)
        if isinstance(incident, CallToolResult):
            return incident
        exp = explain(incident, depth)
        return CallToolResult(
            content=[TextContent(type="text", text=spoken_explanation(incident, exp))],
            structured_content=exp.model_dump(mode="json"),
        )
