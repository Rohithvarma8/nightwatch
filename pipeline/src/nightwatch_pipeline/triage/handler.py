"""Triage Lambda: IncidentChanged → Bedrock summary (grounded) or keep the template.

Never in the request path: the MCP server only reads what this writes.
"""

import os
from datetime import UTC, datetime
from functools import cache
from typing import Any

from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit

from nightwatch_core.models import Summarizer
from nightwatch_core.timefmt import spoken_until
from nightwatch_pipeline import settings as settings_mod
from nightwatch_pipeline.store import Store
from nightwatch_pipeline.triage import agent, rules
from nightwatch_pipeline.triage.templates import TEMPLATE_MODEL

logger = Logger(service="nightwatch-triage")
metrics = Metrics(namespace="NightWatch", service="triage")


def triage_models() -> list[str]:
    return [
        m
        for m in (os.environ.get("TRIAGE_MODEL_ID"), os.environ.get("TRIAGE_FALLBACK_MODEL_ID"))
        if m
    ]


def run(store: Store, incident_id: str, content_hash: str, models: list[str],
        invoke: agent.Invoke = agent.invoke_bedrock) -> dict[str, Any]:  # fmt: skip
    incident = store.get_incident(incident_id)
    if incident is None or incident.status == "resolved":
        return {"outcome": "skipped", "reason": "not active"}
    if incident.content_hash != content_hash:
        return {"outcome": "skipped", "reason": "stale event"}  # a newer event will follow
    signals = store.incident_signals(incident)
    now = datetime.now(UTC)
    d = rules.derive(signals, now)
    members = d.members
    suffix = None
    if incident.replay:
        # Replay prose keeps its original days; the timing comes from the shifted ends_at.
        household = store.get_household(incident.household_id)
        tz = household.tz if household else "UTC"
        suffix = f"In effect until {spoken_until(incident.ends_at, tz, now)}."
    result = agent.summarize(
        members, incident.evidence, models, invoke=invoke, replay=incident.replay,
        spoken_suffix=suffix,
    )  # fmt: skip
    summarizer = Summarizer(
        model=result.model if result.fields else f"{TEMPLATE_MODEL} (after {result.model})",
        latency_ms=result.latency_ms,
        fallback_used=result.fallback_used,
        grounding_passed=result.grounding_passed,
        content_hash=content_hash,
        template_fields=result.template_fields,
    )
    fields: dict[str, Any] = {"summarizer": summarizer.model_dump()}
    if result.fields is not None:
        fields |= result.fields
    saved = store.save_summary(incident_id, content_hash, fields)
    logger.info(
        "triage done",
        extra={"incident_id": incident_id, "saved": saved, "summarizer": summarizer.model_dump(),
               "attempts": result.attempts},
    )  # fmt: skip
    metrics.add_metric("TriageFallback", MetricUnit.Count, 1 if result.fallback_used else 0)
    metrics.add_metric("TriageLatencyMs", MetricUnit.Milliseconds, result.latency_ms)
    return {"outcome": "summarized" if result.fields else "fallback", "saved": saved}


@cache
def _deps() -> tuple[settings_mod.Settings, Store]:
    cfg = settings_mod.load()
    return cfg, Store(cfg.table_name)


@metrics.log_metrics
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    _, store = _deps()
    detail = event["detail"]
    return run(store, detail["incident_id"], detail["content_hash"], triage_models())
