"""Incident builder Lambda.

- EventBridge rule (detail-type "Signal") → group the signal into an incident.
- EventBridge Scheduler every 5 min with {"action": "sweep"} → resolve incidents whose alert ended
  (removes them from the active GSI1).
"""

from datetime import UTC, datetime
from functools import cache
from typing import Any

from aws_lambda_powertools import Logger

from nightwatch_core.models import Signal
from nightwatch_pipeline import settings as settings_mod
from nightwatch_pipeline.incidents.grouping import apply_signal, correlation_key, expire
from nightwatch_pipeline.store import Store

logger = Logger(service="nightwatch-incidents")


def process_signal(store: Store, signal: Signal, now: datetime) -> str:
    household = store.get_household(signal.household_id)
    if household is None:
        raise LookupError(f"unknown household {signal.household_id}")
    existing = store.get_open_incident(signal.household_id, correlation_key(signal))
    updated = apply_signal(existing, signal, household, now)
    if updated is None:
        return "noop"
    if existing is None:
        # Fails (and EventBridge retries) if a concurrent signal created this incident first.
        store.create_incident(updated, "signal_added", now)
        outcome = "created"
    else:
        updated = updated.model_copy(update={"version": existing.version + 1})
        event = "resolved" if updated.status == "resolved" else "signal_added"
        store.update_incident(updated, existing.version, event, now)
        outcome = event if event == "resolved" else "updated"
    logger.info(
        "signal applied",
        extra={"incident_id": updated.id, "outcome": outcome, "signal": signal.external_id},
    )
    return outcome


def sweep(store: Store, household_ids: list[str], now: datetime) -> int:
    resolved = 0
    for household_id in household_ids:
        for incident in store.list_active(household_id):
            done = expire(incident, now)
            if done is None:
                continue
            done = done.model_copy(update={"version": incident.version + 1})
            store.update_incident(done, incident.version, "resolved", now)
            logger.info("incident expired", extra={"incident_id": incident.id})
            resolved += 1
    return resolved


@cache
def _deps() -> tuple[settings_mod.Settings, Store]:
    cfg = settings_mod.load()
    return cfg, Store(cfg.table_name)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    cfg, store = _deps()
    now = datetime.now(UTC)
    if event.get("action") == "sweep":
        return {"resolved": sweep(store, cfg.household_ids, now)}
    signal = Signal.model_validate(event["detail"])
    return {"outcome": process_signal(store, signal, now)}
