"""rollback_deploy: start a CodeDeploy deployment back to the version before the blamed deploy.

Refuses unless confirm=true, unless the incident is a prod incident whose deploy_proximity
evidence names a deploy, and unless that deploy is still the latest one for the service (so it
never "rolls back" a rollback). One outbound call (CodeDeploy CreateDeployment, 2 s timeout).
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Protocol

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field

from nightwatch.domain.incidents import IncidentSource
from nightwatch.tools.common import error, resolve_incident
from nightwatch_core.models import DeployRecord

log = logging.getLogger(__name__)

DESCRIPTION = (
    "Use only when the user explicitly asks to roll back a bad deploy ('roll it back', 'roll "
    "back checkout'). Starts a deployment that returns the service to the version before the "
    "deploy linked to the incident. Requires confirm=true: first ask the user to confirm, then "
    "call again with confirm=true. Refuses if the latest deploy isn't the one linked to the alarm."
)


class Deployer(Protocol):
    def start(self, function: str, current: str, target: str) -> str: ...


class RollbackResult(BaseModel):
    deployment_id: str
    service: str
    from_version: str
    to_version: str
    status: str


def register(server: MCPServer, source: IncidentSource, deployer: Deployer | None) -> None:
    @server.tool(
        name="rollback_deploy",
        title="Roll back a deploy",
        description=DESCRIPTION,
        annotations=ToolAnnotations(
            title="Roll back a deploy",
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=False,
            open_world_hint=True,
        ),  # fmt: skip
    )
    def rollback_deploy(
        confirm: Annotated[
            bool, Field(description="Must be true. Ask the user to confirm before setting it.")
        ],
        incident_id: Annotated[
            str | None, Field(description="Exact incident id from a previous result, if known.")
        ] = None,
        reference: Annotated[
            str | None,
            Field(
                description="How the user referred to the incident, e.g. 'the checkout alarm'.",
                max_length=200,
            ),
        ] = None,  # fmt: skip
    ) -> Annotated[CallToolResult, RollbackResult]:
        now = datetime.now(UTC)
        incident = resolve_incident(source, now, incident_id, reference or "deploy")
        if isinstance(incident, CallToolResult):
            return incident
        blamed = next((r.external_id for r in incident.signals if r.source == "codedeploy"), None)
        service = incident.area_name or ""
        latest: DeployRecord | None = source.latest_deploy(service) if service else None
        if incident.kind != "prod" or blamed is None or latest is None:
            return error(f"The {incident.title} isn't linked to a deploy, so there's nothing to "
                         "roll back.")  # fmt: skip
        if latest.deployment_id != blamed:
            return error(f"{service} has been deployed again since this alarm started, so I "
                         "won't roll it back automatically.")  # fmt: skip
        if not confirm:
            return error(f"To roll back {service} from version {latest.to_version} to "
                         f"{latest.from_version}, ask me again and confirm.")  # fmt: skip
        if deployer is None:
            return error("Rollback isn't configured in this environment.")
        try:
            deployment = deployer.start(service, latest.to_version, latest.from_version)
        except Exception:
            log.exception("rollback failed", extra={"incident_id": incident.id})
            return error(f"I couldn't start the rollback of {service}. Nothing was changed.")
        source.add_event(incident.id, "rollback_started", now, deployment_id=deployment)
        result = RollbackResult(
            deployment_id=deployment, service=service, from_version=latest.to_version,
            to_version=latest.from_version, status="started",
        )  # fmt: skip
        text = (
            f"Rolling back {service} from version {latest.to_version} to {latest.from_version}. "
            "The latency alarm should clear a few minutes after it finishes."
        )
        return CallToolResult(
            content=[TextContent(type="text", text=text)],
            structured_content=result.model_dump(mode="json"),
        )
