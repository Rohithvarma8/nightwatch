"""acknowledge, notify_contact, escalate.

Writes are DynamoDB UpdateItem only; notify/escalate also publish to the SNS fan-out topic (the
one outbound call allowed in the request path, 2 s timeout). Never touches Scheduler: a pending
escalation timer sees the acknowledgement and does nothing.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from nightwatch.domain.actions import (
    NOTIFY_LIMIT_PER_HOUR,
    AckResult,
    EscalateResult,
    NotifyResult,
    channels_phrase,
    contact_not_found,
    describe,
    resolve_contact,
)
from nightwatch.domain.incidents import IncidentSource, Notifier, inline_title
from nightwatch.tools.common import error, resolve_incident
from nightwatch_core.messages import Kind, notification, wire_message
from nightwatch_core.models import Contact, Incident
from nightwatch_core.timefmt import parse_utc

log = logging.getLogger(__name__)

ACK_DESCRIPTION = (
    "Use when the user says they've seen it, got it, are on it, or wants to stop the escalation "
    "('okay, I've got it', 'acknowledge the fire one'). Marks the incident acknowledged, which "
    "cancels the pending escalation to their contact. Safe to repeat. Defaults to the top-ranked "
    "active incident; pass `reference` with the user's words to pick another."
)
NOTIFY_DESCRIPTION = (
    "Use when the user asks to tell, text, message, or alert a person about an incident ('text "
    "my roommate', 'let Priya know about the fire one'). `contact` is the person's name or how "
    "the user refers to them (e.g. 'roommate'). Sends a fixed message built from the incident "
    "(what, where, until when, what to do) by push and email. Limited to 3 messages per contact "
    "per hour."
)
ESCALATE_DESCRIPTION = (
    "Use when the user asks to escalate or to get help now ('escalate this', 'get my roommate "
    "involved'). Marks the incident escalated and immediately notifies the first contact in the "
    "household's escalation policy by push and email."
)
_INCIDENT_ID = Field(description="Exact incident id from a previous result, if known.")
_REFERENCE = Field(
    description="How the user referred to the incident, e.g. 'the fire one'.", max_length=200
)


def _ok(text: str, result: object) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=result.model_dump(mode="json"),  # type: ignore[attr-defined]
    )


def _send(
    source: IncidentSource,
    notifier: Notifier,
    incident: Incident,
    contact: Contact,
    kind: Kind,
    now: datetime,
) -> tuple[str, CallToolResult | None]:
    """Rate limit, build the deterministic message, publish. Returns (body, error)."""
    if not source.take_notify_slot(contact.id, now, NOTIFY_LIMIT_PER_HOUR):
        return "", error(
            f"I've already sent {contact.name} {NOTIFY_LIMIT_PER_HOUR} messages in the last hour, "
            "so I didn't send another one."
        )
    title, body = notification(incident, source.household_tz(), now, kind)
    try:
        notifier.publish(wire_message(kind, incident.household_id, incident.id, contact.id,
                                      title, body))  # fmt: skip
    except Exception:
        log.exception("sns publish failed", extra={"incident_id": incident.id})
        return "", error(f"I couldn't reach the notification service, so {contact.name} "
                         "wasn't notified. Please try again in a minute.")  # fmt: skip
    return body, None


def register(server: MCPServer, source: IncidentSource, notifier: Notifier) -> None:
    @server.tool(
        name="acknowledge",
        title="Acknowledge an incident",
        description=ACK_DESCRIPTION,
        annotations=ToolAnnotations(
            title="Acknowledge an incident",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),  # fmt: skip
    )
    def acknowledge(
        incident_id: Annotated[str | None, _INCIDENT_ID] = None,
        reference: Annotated[str | None, _REFERENCE] = None,
    ) -> Annotated[CallToolResult, AckResult]:
        now = datetime.now(UTC)
        incident = resolve_incident(source, now, incident_id, reference)
        if isinstance(incident, CallToolResult):
            return incident
        pending = (
            incident.status == "open"
            and incident.escalation_due_at is not None
            and parse_utc(incident.escalation_due_at) > now
        )
        updated, changed = source.acknowledge(incident.id, now)
        if updated is None or updated.status == "resolved":
            return error(f"The {inline_title(incident)} is already resolved.")
        if changed:
            source.add_event(incident.id, "acknowledged", now, by="voice")
        result = AckResult(
            id=updated.id, title=updated.title, status=updated.status, acked_at=updated.acked_at,
            escalation_cancelled=pending and changed,
        )  # fmt: skip
        if not changed:
            text = f"The {inline_title(updated)} was already acknowledged."
        elif result.escalation_cancelled:
            text = (
                f"Got it. I've acknowledged the {inline_title(updated)}, "
                "so the escalation is cancelled."
            )
        else:
            text = f"Got it. I've acknowledged the {inline_title(updated)}."
        return _ok(text, result)

    @server.tool(
        name="notify_contact",
        title="Notify a contact",
        description=NOTIFY_DESCRIPTION,
        annotations=ToolAnnotations(
            title="Notify a contact",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        ),  # fmt: skip
    )
    def notify_contact(
        contact: Annotated[
            str,
            Field(
                description="Name or relationship, e.g. 'Priya' or 'roommate'.",
                min_length=1,
                max_length=100,
            ),
        ],  # fmt: skip
        incident_id: Annotated[str | None, _INCIDENT_ID] = None,
        reference: Annotated[str | None, _REFERENCE] = None,
    ) -> Annotated[CallToolResult, NotifyResult]:
        now = datetime.now(UTC)
        person = resolve_contact(source.contacts(), contact)
        if person is None:
            return error(contact_not_found(contact, source.contacts()))
        incident = resolve_incident(source, now, incident_id, reference)
        if isinstance(incident, CallToolResult):
            return incident
        body, failed = _send(source, notifier, incident, person, "notify", now)
        if failed:
            return failed
        source.add_event(incident.id, "notified", now, contact_id=person.id)
        result = NotifyResult(
            queued=True, contact=person.name, relationship=person.aliases[0] if person.aliases
            else None, channels=person.channel_names, message_preview=body,
        )  # fmt: skip
        text = (
            f"Done. I sent {person.name} {channels_phrase(person.channel_names)} about the "
            f"{inline_title(incident)}."
        )
        return _ok(text, result)

    @server.tool(
        name="escalate",
        title="Escalate an incident",
        description=ESCALATE_DESCRIPTION,
        annotations=ToolAnnotations(
            title="Escalate an incident",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        ),  # fmt: skip
    )
    def escalate(
        incident_id: Annotated[str | None, _INCIDENT_ID] = None,
        reference: Annotated[str | None, _REFERENCE] = None,
    ) -> Annotated[CallToolResult, EscalateResult]:
        now = datetime.now(UTC)
        incident = resolve_incident(source, now, incident_id, reference)
        if isinstance(incident, CallToolResult):
            return incident
        policy = source.escalation_policy()
        contacts = {c.id: c for c in source.contacts()}
        first = contacts.get(policy.contact_ids[0]) if policy and policy.contact_ids else None
        if first is None:
            return error("There's no escalation contact set up for this household yet.")
        escalated = source.mark_escalated(incident.id, now)
        if escalated is None:
            return error(f"The {inline_title(incident)} is already resolved.")
        _, failed = _send(source, notifier, escalated, first, "escalation", now)
        if failed:
            return failed
        source.add_event(incident.id, "escalated", now, contact_id=first.id, source="voice")
        result = EscalateResult(
            id=escalated.id, escalated_to=describe(first), channels=first.channel_names,
            status=escalated.status,
        )  # fmt: skip
        text = (
            f"Escalated. I sent {describe(first)} {channels_phrase(first.channel_names)} about "
            f"the {inline_title(incident)}."
        )
        return _ok(text, result)
