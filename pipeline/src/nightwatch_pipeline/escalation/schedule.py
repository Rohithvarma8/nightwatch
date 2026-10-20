"""One-time EventBridge Scheduler schedules for the escalation timer (created by the builder)."""

import json
from datetime import datetime, timedelta

import boto3

from nightwatch_core.models import SEVERITY_RANK, EscalationPolicy, Household, Incident
from nightwatch_core.timefmt import parse_utc

NAME_PREFIX = "nw-esc-"


def needs_escalation(incident: Incident, policy: EscalationPolicy | None) -> bool:
    minimum = policy.min_severity if policy else "high"
    return SEVERITY_RANK[incident.severity] <= SEVERITY_RANK[minimum]


def due_at(incident: Incident, household: Household, now: datetime) -> datetime:
    """started + ack_timeout_s. A live alert's onset can be hours before we learn of it, so the
    clock starts no earlier than now (otherwise it would escalate the moment it's created)."""
    return max(parse_utc(incident.started_at), now) + timedelta(seconds=household.ack_timeout_s)


def schedule_name(incident_id: str) -> str:
    return f"{NAME_PREFIX}{incident_id}"  # ≤ 64 chars


class EscalationScheduler:
    def __init__(self, target_arn: str, role_arn: str) -> None:
        self.target_arn = target_arn
        self.role_arn = role_arn
        self._client = boto3.client("scheduler")

    def create(self, incident: Incident, at: datetime) -> str:
        """Idempotent (a retried signal hits ConflictException). Deletes itself after it fires."""
        name = schedule_name(incident.id)
        try:
            self._client.create_schedule(
                Name=name,
                ScheduleExpression=f"at({at.strftime('%Y-%m-%dT%H:%M:%S')})",
                ScheduleExpressionTimezone="UTC",
                FlexibleTimeWindow={"Mode": "OFF"},
                ActionAfterCompletion="DELETE",
                Target={
                    "Arn": self.target_arn,
                    "RoleArn": self.role_arn,
                    "Input": json.dumps(
                        {"incident_id": incident.id, "household_id": incident.household_id}
                    ),
                    "RetryPolicy": {"MaximumRetryAttempts": 2},
                },
            )
        except self._client.exceptions.ConflictException:
            pass
        return name
