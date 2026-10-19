"""Escalation Lambda: fired by a one-time EventBridge Scheduler schedule at
started + ack_timeout_s (created by the incident builder; deletes itself after it runs).

Re-reads the incident. Acknowledged, resolved, or ended → no-op. Otherwise: status escalated,
notify the first contact in the household's escalation policy, and record a timeline event.
"""

from datetime import UTC, datetime
from functools import cache
from typing import Any

from aws_lambda_powertools import Logger

from nightwatch_core.messages import notification
from nightwatch_core.timefmt import parse_utc
from nightwatch_pipeline import settings as settings_mod
from nightwatch_pipeline.notify.publish import Publisher, SupportsPublish, message
from nightwatch_pipeline.store import Store

logger = Logger(service="nightwatch-escalation")


def escalate(store: Store, publisher: SupportsPublish, incident_id: str, now: datetime) -> str:
    incident = store.get_incident(incident_id)
    if incident is None:
        return "noop: not found"
    if incident.status != "open" or parse_utc(incident.ends_at) <= now:
        return f"noop: {incident.status}"
    policy = store.get_policy(incident.household_id)
    household = store.get_household(incident.household_id)
    if policy is None or not policy.contact_ids or household is None:
        return "noop: no escalation policy"
    if not store.mark_escalated(incident_id, now):
        return "noop: acknowledged meanwhile"  # lost the race to an acknowledge
    contact_id = policy.contact_ids[0]
    title, body = notification(incident, household.tz, now, "escalation")
    publisher.publish(
        message("escalation", incident.household_id, incident_id, contact_id, title, body)
    )
    store.add_event(incident_id, "escalated", now, contact_id=contact_id, source="timer")
    return "escalated"


@cache
def _deps() -> tuple[Store, Publisher]:
    cfg = settings_mod.load()
    return Store(cfg.table_name), Publisher(cfg.notify_topic_arn)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    store, publisher = _deps()
    outcome = escalate(store, publisher, event["incident_id"], datetime.now(UTC))
    logger.info("escalation check", extra={"incident_id": event["incident_id"], "outcome": outcome})
    return {"outcome": outcome}
