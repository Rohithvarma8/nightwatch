"""Notifier Lambda (SNS subscriber): delivers one notification via ntfy push and SES email.

SMS is a documented stub (US SMS needs a registered origination identity; see PLAN.md R6).
Never logs contact details or the ntfy topic.
"""

import json
import os
import urllib.request
from functools import cache
from typing import Any

import boto3
from aws_lambda_powertools import Logger

from nightwatch_core.models import Contact
from nightwatch_pipeline import settings as settings_mod
from nightwatch_pipeline.store import Store

logger = Logger(service="nightwatch-notifier")

NTFY_URL = "https://ntfy.sh/{topic}"
NTFY_TIMEOUT_S = 3


def send_ntfy(topic: str, title: str, body: str, priority: str) -> None:
    req = urllib.request.Request(
        NTFY_URL.format(topic=topic),
        data=body.encode(),
        method="POST",
        headers={
            "Title": title.encode("ascii", "ignore").decode(),  # HTTP headers: ASCII only
            "Priority": "high" if priority == "high" else "default",
            "Tags": "warning",
        },
    )
    with urllib.request.urlopen(req, timeout=NTFY_TIMEOUT_S) as resp:  # noqa: S310 (fixed https)
        if resp.status >= 300:
            raise RuntimeError(f"ntfy HTTP {resp.status}")


def send_email(ses: Any, sender: str, to: str, title: str, body: str) -> None:
    ses.send_email(
        FromEmailAddress=sender,
        Destination={"ToAddresses": [to]},
        Content={
            "Simple": {
                "Subject": {"Data": f"Night Watch: {title}"},
                "Body": {"Text": {"Data": body}},
            }
        },
    )


def deliver(
    msg: dict[str, Any], contact: Contact, ntfy_topic: str | None, ses: Any, sender: str | None
) -> dict[str, str]:
    """Try every channel the contact has. Returns {channel: "sent" | error}."""
    results: dict[str, str] = {}
    if contact.channels.ntfy and ntfy_topic:
        try:
            send_ntfy(ntfy_topic, msg["title"], msg["body"], msg["priority"])
            results["push"] = "sent"
        except Exception as e:
            results["push"] = f"error: {type(e).__name__}"
    if contact.channels.email and sender:
        try:
            send_email(ses, sender, contact.channels.email, msg["title"], msg["body"])
            results["email"] = "sent"
        except Exception as e:
            results["email"] = f"error: {type(e).__name__}"
    if contact.channels.sms:
        results["sms"] = "stub: not sent"
    return results


@cache
def _deps() -> tuple[Store, str | None, Any, str | None]:
    cfg = settings_mod.load()
    topic = None
    if param := os.environ.get("NTFY_TOPIC_PARAM"):  # SSM SecureString, read once at init
        topic = boto3.client("ssm").get_parameter(Name=param, WithDecryption=True)["Parameter"][
            "Value"
        ]
    return Store(cfg.table_name), topic, boto3.client("sesv2"), os.environ.get("SES_SENDER")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    store, topic, ses, sender = _deps()
    outcomes = []
    for record in event["Records"]:
        msg = json.loads(record["Sns"]["Message"])
        contact = store.get_contact(msg["household_id"], msg["contact_id"])
        if contact is None:
            logger.warning("unknown contact", extra={"incident_id": msg["incident_id"]})
            continue
        results = deliver(msg, contact, topic, ses, sender)
        logger.info(
            "notification delivered",
            extra={"incident_id": msg["incident_id"], "kind": msg["kind"], "results": results},
        )
        if not any(v == "sent" for v in results.values()):
            raise RuntimeError(f"no channel delivered: {results}")  # SNS/Lambda retries
        outcomes.append(results)
    return {"delivered": outcomes}
