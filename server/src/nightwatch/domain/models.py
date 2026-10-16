"""Pydantic models for the tool-facing incident shape (DESIGN.md §2)."""

from typing import Literal

from pydantic import BaseModel, Field

from nightwatch_core.models import SEVERITY_RANK, Kind, Severity, Status

__all__ = [
    "SEVERITY_RANK",
    "ActiveIncidents",
    "IncidentView",
    "Kind",
    "Scope",
    "Severity",
    "Status",
]

Scope = Literal["all", "home", "work"]


class IncidentView(BaseModel):
    id: str
    kind: Kind
    title: str
    severity: Severity
    status: Status
    started_at: str
    spoken_summary: str
    top_action: str
    evidence_preview: list[str]
    escalation_due_at: str | None
    replay: bool
    replay_original_time: str | None


class ActiveIncidents(BaseModel):
    as_of: str
    household: str
    spoken_overview: str
    incidents: list[IncidentView] = Field(default_factory=list)
