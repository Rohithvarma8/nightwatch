"""Prod normalizer: CloudWatch Alarm State Change + CodeDeploy deployment events (default bus)
→ Signal (kind prod) → dedupe → nightwatch bus. Same claim/publish path as the NWS ingester.

- Alarm → ALARM is an "Alert", → OK a "Cancel" (resolves the incident). INSUFFICIENT_DATA ignored.
- Deploy SUCCESS → a deploy signal (the builder stores SVC#/DEPLOY# and uses it for proximity).
  The event has no versions, and GetDeployment returns only the AppSpec's sha256 (not its
  content), so versions come from the deployment target: ListDeploymentTargets →
  GetDeploymentTarget → lambdaTarget.lambdaFunctionInfo (currentVersion → targetVersion).
"""

import json
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any

import boto3
from aws_lambda_powertools import Logger
from botocore.config import Config

from nightwatch_core.ids import new_id
from nightwatch_core.models import Signal
from nightwatch_core.timefmt import to_utc_iso
from nightwatch_pipeline import settings as settings_mod
from nightwatch_pipeline.bus import Bus
from nightwatch_pipeline.store import Store

logger = Logger(service="nightwatch-ingest-prod")

ALARM_TTL = timedelta(days=7)  # an incident that stays in ALARM this long expires via the sweep
CONSOLE = "https://{region}.console.aws.amazon.com"


def parse_aws_time(value: str) -> datetime:
    """'2026-10-20T01:02:03.456+0000' (CloudWatch), '…Z', or ISO with offset."""
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value.replace("Z", "+0000"), fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(value)


def normalize_alarm(
    event: dict[str, Any], household_id: str, observed_at: datetime
) -> Signal | None:
    d = event["detail"]
    state = d["state"]["value"]
    if state not in ("ALARM", "OK"):
        return None
    metric = d["configuration"]["metrics"][0]["metricStat"]
    dims = metric["metric"].get("dimensions", {})
    service = dims.get("FunctionName") or d["alarmName"]
    name = metric["metric"]["name"]
    reason_data = json.loads(d["state"].get("reasonData") or "{}")
    sent = parse_aws_time(d["state"]["timestamp"])
    threshold = reason_data.get("threshold")
    region = event.get("region", "us-west-2")
    return Signal(
        id=new_id("sig"),
        household_id=household_id,
        source="cloudwatch",
        kind="prod",
        external_id=f"{d['alarmName']}#{d['state']['timestamp']}",
        event=f"{service} latency" if name == "Duration" else f"{service} {name}",
        hazard_family="prod",
        severity="moderate",  # raised to high by deploy proximity (rules.py)
        area=service,
        area_name=service,
        headline=f"{d['alarmName']} is {state}: {d['state']['reason']}",
        description=d["configuration"].get("description") or "",
        sender_name="CloudWatch",
        message_type="Alert" if state == "ALARM" else "Cancel",
        sent_at=to_utc_iso(sent),
        onset_at=to_utc_iso(sent),
        ends_at=to_utc_iso(sent + ALARM_TTL),
        observed_at=to_utc_iso(observed_at),
        url=f"{CONSOLE.format(region=region)}/cloudwatch/home?region={region}#alarmsV2:alarm/"
        f"{d['alarmName']}",
        nws_certainty="Observed",
        attributes={
            "alarm_name": d["alarmName"],
            "state": state,
            "metric": name,
            "statistic": metric.get("stat", ""),
            "threshold": f"{threshold:g}" if isinstance(threshold, int | float) else "",
            "period_s": str(metric.get("period", "")),
        },
    )


def normalize_deploy(
    event: dict[str, Any],
    info: dict[str, Any],
    lambda_target: dict[str, Any],
    household_id: str,
    observed_at: datetime,
) -> Signal | None:
    """`info` = GetDeployment deploymentInfo; `lambda_target` = GetDeploymentTarget
    deploymentTarget.lambdaTarget (has lambdaFunctionInfo with the versions)."""
    d = event["detail"]
    if d["state"] != "SUCCESS":
        return None
    fn = lambda_target["lambdaFunctionInfo"]
    service, from_v, to_v = fn["functionName"], str(fn["currentVersion"]), str(fn["targetVersion"])
    ended = info.get("completeTime") or parse_aws_time(event["time"])
    ended = ended if isinstance(ended, datetime) else parse_aws_time(str(ended))
    region = event.get("region", "us-west-2")
    dep = d["deploymentId"]
    return Signal(
        id=new_id("sig"),
        household_id=household_id,
        source="codedeploy",
        kind="prod",
        external_id=dep,
        event="Deployment",
        hazard_family="prod",
        severity="low",
        area=service,
        area_name=service,
        headline=f"Deployment {dep} of {service} from version {from_v} to {to_v} succeeded.",
        sender_name="CodeDeploy",
        message_type="Alert",
        sent_at=to_utc_iso(ended),
        ends_at=to_utc_iso(ended),
        observed_at=to_utc_iso(observed_at),
        url=f"{CONSOLE.format(region=region)}/codesuite/codedeploy/deployments/{dep}?region={region}",
        attributes={
            "deployment_id": dep,
            "from_version": from_v,
            "to_version": to_v,
            "application": d.get("application", ""),
            "deployment_group": d.get("deploymentGroup", ""),
        },
    )


@cache
def _deps() -> tuple[settings_mod.Settings, Store, Bus, Any]:
    cfg = settings_mod.load()
    codedeploy = boto3.client(
        "codedeploy", config=Config(read_timeout=5, retries={"max_attempts": 3})
    )
    return cfg, Store(cfg.table_name), Bus(cfg.bus_name), codedeploy


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    cfg, store, bus, codedeploy = _deps()
    logger.info("prod event", extra={"source": event.get("source"), "event": event})
    now = datetime.now(UTC)
    household_id = cfg.household_ids[0]
    if event.get("source") == "aws.cloudwatch":
        signal = normalize_alarm(event, household_id, now)
    elif event.get("source") == "aws.codedeploy":
        if event["detail"]["state"] != "SUCCESS":
            return {"outcome": f"ignored {event['detail']['state']}"}
        dep = event["detail"]["deploymentId"]
        info = codedeploy.get_deployment(deploymentId=dep)["deploymentInfo"]
        (target_id,) = codedeploy.list_deployment_targets(deploymentId=dep)["targetIds"]
        target = codedeploy.get_deployment_target(deploymentId=dep, targetId=target_id)
        signal = normalize_deploy(
            event, info, target["deploymentTarget"]["lambdaTarget"], household_id, now
        )
    else:
        return {"outcome": "ignored source"}
    if signal is None:
        return {"outcome": "ignored state"}
    if not store.claim_signal(signal, now):
        return {"outcome": "duplicate"}
    if bus.publish([signal]):
        store.release_signal(signal.source, signal.external_id)
        raise RuntimeError("PutEvents failed; claim released")
    return {"outcome": "published", "signal": signal.external_id}
