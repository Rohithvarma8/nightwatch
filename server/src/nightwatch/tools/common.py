"""Shared tool plumbing: resolve which incident the user means, error results."""

from datetime import datetime

from mcp_types import CallToolResult, TextContent

from nightwatch.domain.incidents import IncidentSource, candidates, is_active
from nightwatch.domain.resolve import match_reference, not_found_message
from nightwatch_core.models import Incident


def error(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)


def resolve_incident(
    source: IncidentSource, now: datetime, incident_id: str | None, reference: str | None
) -> Incident | CallToolResult:
    """By id, else by fuzzy reference, else the top-ranked incident. Errors list active ones."""
    active = [i for i in source.active_incidents(now) if is_active(i, now)]
    ordered = candidates(active, now)
    if incident_id:
        found = next((i for i in ordered if i.id == incident_id), None)
        found = found or source.get_incident(incident_id)
        return found or error(not_found_message(None, ordered))
    if reference:
        return match_reference(ordered, reference) or error(not_found_message(reference, ordered))
    if not ordered:
        return error("Nothing is active right now, so there's nothing to explain.")
    return ordered[0]
