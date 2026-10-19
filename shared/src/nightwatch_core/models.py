"""Domain models (DESIGN.md §3). Timestamps are UTC ISO-8601 strings ending in Z."""

from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["hazard", "prod"]
Severity = Literal["critical", "high", "moderate", "low"]
Status = Literal["open", "acknowledged", "escalated", "resolved"]
Source = Literal["nws", "airnow", "fire", "cloudwatch", "codedeploy"]
HazardFamily = Literal["fire_weather", "wind", "heat", "cold", "coastal", "air", "other"]

SEVERITY_RANK: dict[Severity, int] = {"critical": 0, "high": 1, "moderate": 2, "low": 3}


class Zone(BaseModel):
    id: str  # NWS UGC code, e.g. "CAZ374"
    name: str  # e.g. "Southeastern Ventura County Valleys"


class Household(BaseModel):
    id: str
    name: str
    tz: str
    lat: float
    lon: float
    location: str
    forecast_zone: Zone
    fire_zone: Zone
    county: str | None = None  # NWS county zone, e.g. "CAC111"
    ack_timeout_s: int = 300


class Signal(BaseModel):
    """One normalized source event (an NWS alert message, an AQI reading, an alarm change)."""

    id: str
    household_id: str
    source: Source
    external_id: str
    event: str
    hazard_family: HazardFamily
    severity: Severity
    area: str  # household zone the alert matched (correlation key part)
    area_name: str  # place name as it appears in the source
    headline: str
    description: str = ""  # full source text: the triage agent's only input, and grounding source
    instruction: str = ""
    sender_name: str
    message_type: Literal["Alert", "Update", "Cancel"]
    sent_at: str
    onset_at: str | None = None
    ends_at: str
    observed_at: str
    url: str
    nws_severity: str | None = None
    nws_urgency: str | None = None
    nws_certainty: str | None = None
    references: list[str] = Field(default_factory=list)
    replay: bool = False
    replay_original_time: str | None = None


class SignalRef(BaseModel):
    source: Source
    external_id: str
    observed_at: str  # when the source issued it
    summary: str
    url: str
    event: str | None = None
    hazard_family: HazardFamily | None = None
    message_type: str | None = None
    certainty: str | None = None
    ends_at: str | None = None
    role: Literal["primary", "supporting"] = "primary"


class Evidence(BaseModel):
    type: str
    detail: str
    weight: float
    source_url: str | None = None


class Summarizer(BaseModel):
    model: str
    latency_ms: int
    fallback_used: bool
    grounding_passed: bool | None = None  # None = template (nothing to check)
    content_hash: str | None = None  # incident content this summary was written for
    template_fields: list[str] = Field(default_factory=list)  # AI fields rejected (e.g. a URL)


class Incident(BaseModel):
    id: str
    household_id: str
    kind: Kind
    title: str
    severity: Severity
    status: Status
    started_at: str
    updated_at: str
    ends_at: str  # incident stops being active after this (alert `ends`, else `expires`)
    resolved_at: str | None = None
    correlation_key: str
    related_keys: list[str] = Field(default_factory=list)  # other OPENKEYs that point here
    merged_into: str | None = None  # set when resolved by merging into another incident
    content_hash: str = ""  # changes when the incident's facts change → re-summarize
    signals: list[SignalRef] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    spoken_summary: str
    detail_summary: str
    recommended_actions: list[str] = Field(default_factory=list)
    runbook_id: str | None = None
    acked_by: str | None = None
    acked_at: str | None = None
    escalation_schedule_name: str | None = None
    replay: bool = False
    replay_original_time: str | None = None
    summarizer: Summarizer
    version: int = 0  # optimistic locking for concurrent signal writes

    @property
    def top_action(self) -> str:
        return self.recommended_actions[0] if self.recommended_actions else ""

    @property
    def keys(self) -> list[str]:
        return [self.correlation_key, *self.related_keys]

    @property
    def hazard_families(self) -> set[str]:
        if self.kind == "prod":
            return {"prod"}
        return {r.hazard_family for r in self.signals if r.hazard_family} or {"other"}
