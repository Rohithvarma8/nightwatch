"""Incident builder Lambda.

- EventBridge rule (detail-type "Signal") → fold the signal into its incident (rules.py).
- EventBridge Scheduler every 5 min with {"action": "sweep"} → re-derive active incidents
  (expire ended alerts, drop them from GSI1) and reconcile fire-risk merges.
After any content change it publishes IncidentChanged so the triage agent re-summarizes.
"""

from datetime import UTC, datetime
from functools import cache
from typing import Any

from aws_lambda_powertools import Logger

from nightwatch_core.ids import new_id
from nightwatch_core.models import Household, Incident, Signal
from nightwatch_core.timefmt import parse_utc, to_utc_iso
from nightwatch_pipeline import settings as settings_mod
from nightwatch_pipeline.bus import Bus
from nightwatch_pipeline.store import Store
from nightwatch_pipeline.triage import rules, templates

logger = Logger(service="nightwatch-incidents")


def _new_incident(signal: Signal, household: Household, now: datetime) -> Incident:
    shell = Incident(
        id=new_id("inc"),
        household_id=signal.household_id,
        kind="hazard",
        title=signal.event,
        severity=signal.severity,
        status="open",
        started_at=signal.onset_at or signal.sent_at,
        updated_at=to_utc_iso(now),
        ends_at=signal.ends_at,
        correlation_key=rules.correlation_key(signal),
        spoken_summary="",
        detail_summary="",
        replay=signal.replay,
        replay_original_time=signal.replay_original_time,
        summarizer=templates.summarizer(),
    )
    return rules.apply_derived(shell, [signal], household, now)


def _bumped(incident: Incident, prev: Incident) -> Incident:
    return incident.model_copy(update={"version": prev.version + 1})


def process_signal(store: Store, signal: Signal, now: datetime) -> tuple[str, list[Incident]]:
    """Returns (outcome, incidents whose content changed)."""
    household = store.get_household(signal.household_id)
    if household is None:
        raise LookupError(f"unknown household {signal.household_id}")
    key = rules.correlation_key(signal)
    target = store.get_open_incident(signal.household_id, key)
    new_keys: list[str] = []
    if target is None:
        active = store.list_active_with_signals(signal.household_id)
        target = rules.find_fire_incident_for_wind(signal, active, now)
        if target is not None:
            new_keys = [key]
    if target is None:
        if signal.message_type == "Cancel" or parse_utc(signal.ends_at) <= now:
            return "noop", []
        created = _new_incident(signal, household, now)
        store.create_incident(created, "signal_added", now)
        outcome, changed = "created", [created]
    elif any(r.external_id == signal.external_id for r in target.signals):
        return "noop", []  # redelivered event
    else:
        signals = [*store.incident_signals(target), signal]
        updated = rules.apply_derived(target, signals, household, now)
        if new_keys:
            updated = updated.model_copy(update={"related_keys": [*target.related_keys, *new_keys]})
        updated = _bumped(updated, target)
        event = "resolved" if updated.status == "resolved" else "signal_added"
        store.update_incident(updated, target.version, event, now, new_keys=new_keys)
        outcome = (
            "joined_fire_risk" if new_keys else ("resolved" if event == "resolved" else "updated")
        )
        changed = [updated] if updated.content_hash != target.content_hash else []
    logger.info("signal applied", extra={"outcome": outcome, "signal": signal.external_id})
    return outcome, changed + reconcile(store, household, now)


def reconcile(store: Store, household: Household, now: datetime) -> list[Incident]:
    """Merge standalone wind incidents into overlapping fire incidents (rules.merge_plan)."""
    changed: list[Incident] = []
    active = store.list_active_with_signals(household.id)
    signals_by_id = {inc.id: sigs for inc, sigs in active}
    for stale_fire, stale_wind in rules.merge_plan(active, now):
        # GSI1 reads are eventually consistent: re-read for current versions before writing.
        fire_inc = store.get_incident(stale_fire.id) or stale_fire
        wind_inc = store.get_incident(stale_wind.id) or stale_wind
        merged = rules.apply_derived(
            fire_inc, signals_by_id[fire_inc.id] + signals_by_id[wind_inc.id], household, now
        ).model_copy(update={"related_keys": [*fire_inc.related_keys, *wind_inc.keys]})
        closed = wind_inc.model_copy(
            update={
                "status": "resolved",
                "resolved_at": to_utc_iso(now),
                "updated_at": to_utc_iso(now),
                "merged_into": fire_inc.id,
            }
        )
        store.merge_incidents(
            _bumped(merged, fire_inc),
            fire_inc.version,
            _bumped(closed, wind_inc),
            wind_inc.version,
            now,
        )
        logger.info("merged", extra={"incident_id": fire_inc.id, "merged": wind_inc.id})
        changed.append(merged)
    return changed


def sweep(store: Store, household_ids: list[str], now: datetime) -> tuple[int, list[Incident]]:
    """Re-derive every active incident; resolve ended ones; reconcile merges."""
    resolved = 0
    changed: list[Incident] = []
    for household_id in household_ids:
        household = store.get_household(household_id)
        if household is None:
            continue
        for incident, signals in store.list_active_with_signals(household_id):
            if not signals:
                continue
            updated = rules.apply_derived(incident, signals, household, now)
            if updated.updated_at == incident.updated_at:
                continue  # nothing changed
            updated = _bumped(updated, incident)
            event = "resolved" if updated.status == "resolved" else "rederived"
            store.update_incident(updated, incident.version, event, now)
            if updated.status == "resolved":
                resolved += 1
                logger.info("incident expired", extra={"incident_id": incident.id})
            elif updated.content_hash != incident.content_hash:
                changed.append(updated)
        changed += reconcile(store, household, now)
    return resolved, changed


@cache
def _deps() -> tuple[settings_mod.Settings, Store, Bus]:
    cfg = settings_mod.load()
    return cfg, Store(cfg.table_name), Bus(cfg.bus_name)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    cfg, store, bus = _deps()
    now = datetime.now(UTC)
    if event.get("action") == "sweep":
        resolved, changed = sweep(store, cfg.household_ids, now)
        result: dict[str, Any] = {"resolved": resolved}
    else:
        outcome, changed = process_signal(store, Signal.model_validate(event["detail"]), now)
        result = {"outcome": outcome}
    open_changed = [i for i in changed if i.status != "resolved"]
    bus.publish_incident_changed(open_changed)
    return result | {"incident_changed": len(open_changed)}
