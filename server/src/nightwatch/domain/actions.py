"""acknowledge / notify_contact / escalate: contact resolution, results, spoken text. Pure."""

import re

from pydantic import BaseModel

from nightwatch_core.models import Contact

NOTIFY_LIMIT_PER_HOUR = 3


class AckResult(BaseModel):
    id: str
    title: str
    status: str
    acked_at: str | None
    escalation_cancelled: bool


class NotifyResult(BaseModel):
    queued: bool  # handed to the notifier (SNS); delivery happens async
    contact: str
    relationship: str | None
    channels: list[str]
    message_preview: str


class EscalateResult(BaseModel):
    id: str
    escalated_to: str
    channels: list[str]
    status: str


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def resolve_contact(contacts: list[Contact], reference: str) -> Contact | None:
    """By name or alias, case-insensitive: "Priya", "my roommate", "the roommate"."""
    ref = f" {_norm(reference)} "
    for c in sorted(contacts, key=lambda c: c.escalation_order):
        names = [c.name, *c.aliases]
        if any(f" {_norm(n)} " in ref for n in names if _norm(n)):
            return c
    return None


def describe(contact: Contact) -> str:
    """'Priya (roommate)'."""
    return f"{contact.name} ({contact.aliases[0]})" if contact.aliases else contact.name


def contact_not_found(reference: str, contacts: list[Contact]) -> str:
    if not contacts:
        return f"I couldn't find '{reference}', and no contacts are set up yet."
    known = "; ".join(describe(c) for c in contacts)
    return f"I couldn't find a contact called '{reference}'. Your contacts: {known}."


def channels_phrase(channels: list[str]) -> str:
    words = {"push": "a push notification", "email": "an email"}
    parts = [words.get(c, c) for c in channels]
    return " and ".join(parts) if parts else "a message"
