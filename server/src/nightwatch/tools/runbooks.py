"""get_runbook tool."""

from datetime import UTC, datetime
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field

from nightwatch.domain.incidents import IncidentSource, spoken_title
from nightwatch.domain.runbooks import Runbook, runbook_for
from nightwatch.tools.common import error, resolve_incident

DESCRIPTION = (
    "Use when the user asks what to do, what the next step is, or how to handle an incident "
    "('what should I do?', 'what do I do about the wind thing?'). Defaults to the top-ranked "
    "active incident; pass `reference` with the user's words to pick another. Returns the next "
    "step and the full checklist, each step with why it matters."
)


class RunbookStepView(BaseModel):
    n: int
    action: str
    why: str
    done: bool


class RunbookView(BaseModel):
    runbook_id: str
    title: str
    incident_id: str
    incident_title: str
    next_step: str
    steps: list[RunbookStepView]


def _view(book: Runbook, incident_id: str, incident_title: str) -> RunbookView:
    steps = [
        RunbookStepView(n=n, action=s.action, why=s.why, done=False)
        for n, s in enumerate(book.steps, start=1)
    ]
    return RunbookView(
        runbook_id=book.id,
        title=book.title,
        incident_id=incident_id,
        incident_title=incident_title,
        next_step=steps[0].action,
        steps=steps,
    )


def _spoken(view: RunbookView, heading: str) -> str:
    text = f"For the {heading}: first, {view.steps[0].action.lower()}."
    if len(view.steps) > 1:
        text += f" Then, {view.steps[1].action.lower()}."
    return text + f" That's {len(view.steps)} steps in all."


def register(server: MCPServer, source: IncidentSource, runbooks: dict[str, Runbook]) -> None:
    @server.tool(
        name="get_runbook",
        title="Runbook for an incident",
        description=DESCRIPTION,
        annotations=ToolAnnotations(
            title="Runbook for an incident",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    def get_runbook(
        incident_id: Annotated[
            str | None, Field(description="Exact incident id from a previous result, if known.")
        ] = None,
        reference: Annotated[
            str | None,
            Field(
                description="How the user referred to the incident, e.g. 'the fire one'.",
                max_length=200,
            ),
        ] = None,
    ) -> Annotated[CallToolResult, RunbookView]:
        now = datetime.now(UTC)
        incident = resolve_incident(source, now, incident_id, reference)
        if isinstance(incident, CallToolResult):
            return incident
        book = runbook_for(incident, runbooks)
        if book is None:
            return error(f"I don't have a runbook for the {spoken_title(incident)} yet.")
        view = _view(book, incident.id, incident.title)
        return CallToolResult(
            content=[TextContent(type="text", text=_spoken(view, spoken_title(incident).lower()))],
            structured_content=view.model_dump(mode="json"),
        )
