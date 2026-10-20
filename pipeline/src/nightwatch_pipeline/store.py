"""DynamoDB access for the pipeline (DESIGN.md §3). The only module here that touches the table."""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from pydantic import BaseModel

from nightwatch_core import keys
from nightwatch_core.ids import new_id
from nightwatch_core.models import (
    Contact,
    DeployRecord,
    EscalationPolicy,
    Household,
    Incident,
    Signal,
)

SIGNAL_TTL = timedelta(days=7)
RESOLVED_TTL = timedelta(days=30)


def _attrs(model: BaseModel) -> dict[str, Any]:
    """Pydantic → DynamoDB-safe dict (floats as Decimal)."""
    return json.loads(model.model_dump_json(), parse_float=Decimal)


def incident_item(inc: Incident, now: datetime) -> dict[str, Any]:
    item = {"PK": keys.incident_pk(inc.id), "SK": keys.META, "entity": "incident", **_attrs(inc)}
    if inc.status == "resolved":
        item["expires_at"] = int((now + RESOLVED_TTL).timestamp())
    else:  # sparse GSI1: only active incidents are indexed
        item["GSI1PK"] = keys.active_gsi1_pk(inc.household_id)
        item["GSI1SK"] = keys.active_gsi1_sk(inc.severity, inc.started_at)
    return item


class Store:
    def __init__(self, table_name: str) -> None:
        self.table_name = table_name
        resource: Any = boto3.resource("dynamodb")  # boto3 resources are untyped
        self.table = resource.Table(table_name)
        self._client = self.table.meta.client

    # --- households --------------------------------------------------------
    def put_household(self, household: Household) -> None:
        self.table.put_item(
            Item={
                "PK": keys.household_pk(household.id),
                "SK": keys.PROFILE,
                "entity": "household",
                **_attrs(household),
            }
        )

    def get_household(self, household_id: str) -> Household | None:
        item = self.table.get_item(
            Key={"PK": keys.household_pk(household_id), "SK": keys.PROFILE}
        ).get("Item")
        return Household.model_validate(item) if item else None

    # --- contacts + escalation policy ---------------------------------------
    def put_contact(self, contact: Contact) -> None:
        self.table.put_item(
            Item={
                "PK": keys.household_pk(contact.household_id),
                "SK": keys.contact_sk(contact.id),
                "entity": "contact",
                **_attrs(contact),
            }
        )

    def get_contact(self, household_id: str, contact_id: str) -> Contact | None:
        item = self.table.get_item(
            Key={"PK": keys.household_pk(household_id), "SK": keys.contact_sk(contact_id)}
        ).get("Item")
        return Contact.model_validate(item) if item else None

    def put_policy(self, policy: EscalationPolicy) -> None:
        self.table.put_item(
            Item={
                "PK": keys.household_pk(policy.household_id),
                "SK": keys.ESCALATION_POLICY,
                "entity": "policy",
                **_attrs(policy),
            }
        )

    def get_policy(self, household_id: str) -> EscalationPolicy | None:
        item = self.table.get_item(
            Key={"PK": keys.household_pk(household_id), "SK": keys.ESCALATION_POLICY}
        ).get("Item")
        return EscalationPolicy.model_validate(item) if item else None

    def mark_escalated(self, incident_id: str, now: datetime) -> bool:
        """open → escalated, atomically. False if acknowledged, resolved, or already escalated."""
        at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            self.table.update_item(
                Key={"PK": keys.incident_pk(incident_id), "SK": keys.META},
                UpdateExpression="SET #s = :esc, escalated_at = :at, updated_at = :at, "
                "#v = #v + :one",
                ConditionExpression="#s = :open",
                ExpressionAttributeNames={"#s": "status", "#v": "version"},
                ExpressionAttributeValues={
                    ":esc": "escalated",
                    ":open": "open",
                    ":at": at,
                    ":one": 1,
                },
            )
        except self._client.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def add_event(self, incident_id: str, event_type: str, now: datetime, **detail: Any) -> None:
        at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.table.put_item(
            Item={
                "PK": keys.incident_pk(incident_id),
                "SK": keys.event_sk(at, new_id("evt")),
                "entity": "incident_event",
                "type": event_type,
                "at": at,
                **detail,
            }
        )

    # --- deploys (prod correlation) ------------------------------------------
    def put_deploy(self, record: DeployRecord) -> None:
        self.table.put_item(
            Item={
                "PK": keys.service_pk(record.service),
                "SK": keys.deploy_sk(record.ended_at, record.deployment_id),
                "entity": "deploy",
                **_attrs(record),
            }
        )

    def deploys_between(self, service: str, start: str, end: str) -> list[DeployRecord]:
        """Deploys of `service` that ended in [start, end] (ISO UTC)."""
        resp = self.table.query(
            KeyConditionExpression=Key("PK").eq(keys.service_pk(service))
            & Key("SK").between(f"DEPLOY#{start}", f"DEPLOY#{end}#~")
        )
        return [DeployRecord.model_validate(i) for i in resp.get("Items", [])]

    # --- signals (dedupe + the record the builder and triage read) ---------
    def claim_signal(self, signal: Signal, now: datetime) -> bool:
        """Conditional put of the full signal on SIG#<source>#<id>. False if already seen."""
        try:
            self.table.put_item(
                Item={
                    "PK": keys.signal_pk(signal.source, signal.external_id),
                    "SK": keys.META,
                    "entity": "signal",
                    "first_seen_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "expires_at": int((now + SIGNAL_TTL).timestamp()),
                    **_attrs(signal),
                },
                ConditionExpression="attribute_not_exists(PK)",
            )
        except self._client.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def get_signals(self, refs: list[tuple[str, str]]) -> list[Signal]:
        """Full signals for (source, external_id) pairs. Missing ones (TTL'd) are skipped."""
        found: list[Signal] = []
        unique = list(dict.fromkeys(refs))
        for start in range(0, len(unique), 100):
            request = {
                self.table_name: {
                    "Keys": [
                        {"PK": keys.signal_pk(src, ext), "SK": keys.META}
                        for src, ext in unique[start : start + 100]
                    ],
                    "ConsistentRead": True,
                }
            }
            while request:
                resp = self._client.batch_get_item(RequestItems=request)
                found += [
                    Signal.model_validate(i) for i in resp["Responses"].get(self.table_name, [])
                ]
                request = resp.get("UnprocessedKeys") or None
        return found

    def incident_signals(self, incident: Incident) -> list[Signal]:
        return self.get_signals([(r.source, r.external_id) for r in incident.signals])

    def list_active_with_signals(self, household_id: str) -> list[tuple[Incident, list[Signal]]]:
        return [(i, self.incident_signals(i)) for i in self.list_active(household_id)]

    def release_signal(self, source: str, external_id: str) -> None:
        """Undo a claim when publishing fails, so the next run retries it."""
        self.table.delete_item(Key={"PK": keys.signal_pk(source, external_id), "SK": keys.META})

    # --- incidents ---------------------------------------------------------
    def get_open_incident(self, household_id: str, correlation_key: str) -> Incident | None:
        link = self.table.get_item(
            Key={"PK": keys.household_pk(household_id), "SK": keys.openkey_sk(correlation_key)},
            ConsistentRead=True,
        ).get("Item")
        if not link:
            return None
        item = self.table.get_item(
            Key={"PK": keys.incident_pk(str(link["incident_id"])), "SK": keys.META},
            ConsistentRead=True,
        ).get("Item")
        return Incident.model_validate(item) if item else None

    def get_incident(self, incident_id: str) -> Incident | None:
        item = self.table.get_item(
            Key={"PK": keys.incident_pk(incident_id), "SK": keys.META}, ConsistentRead=True
        ).get("Item")
        return Incident.model_validate(item) if item else None

    def list_active(self, household_id: str) -> list[Incident]:
        resp = self.table.query(
            IndexName=keys.GSI1,
            KeyConditionExpression=Key("GSI1PK").eq(keys.active_gsi1_pk(household_id)),
        )
        return [Incident.model_validate(i) for i in resp.get("Items", [])]

    def create_incident(self, inc: Incident, event_type: str, now: datetime) -> None:
        """New incident + OPENKEY link. Fails if another writer created the link first."""
        self._client.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": self.table_name,
                        "Item": incident_item(inc, now),
                        "ConditionExpression": "attribute_not_exists(PK)",
                    }
                },
                {
                    "Put": {
                        "TableName": self.table_name,
                        "Item": {
                            "PK": keys.household_pk(inc.household_id),
                            "SK": keys.openkey_sk(inc.correlation_key),
                            "entity": "openkey",
                            "incident_id": inc.id,
                        },
                        "ConditionExpression": "attribute_not_exists(PK)",
                    }
                },
                {"Put": {"TableName": self.table_name, "Item": self._event(inc, event_type, now)}},
            ]
        )

    def _put_versioned(self, inc: Incident, prev_version: int, now: datetime) -> dict[str, Any]:
        return {
            "Put": {
                "TableName": self.table_name,
                "Item": incident_item(inc, now),
                "ConditionExpression": "version = :v",
                "ExpressionAttributeValues": {":v": prev_version},
            }
        }

    def _openkey_put(self, household_id: str, key: str, incident_id: str) -> dict[str, Any]:
        return {
            "Put": {
                "TableName": self.table_name,
                "Item": {
                    "PK": keys.household_pk(household_id),
                    "SK": keys.openkey_sk(key),
                    "entity": "openkey",
                    "incident_id": incident_id,
                },
            }
        }

    def update_incident(
        self,
        inc: Incident,
        prev_version: int,
        event_type: str,
        now: datetime,
        new_keys: list[str] | None = None,
    ) -> None:
        """Replace the incident if nobody else wrote it since `prev_version`.

        `new_keys` get OPENKEY links to this incident (e.g. a wind key joining a fire risk).
        Resolving drops the GSI1 attributes (leaves the active index) and all its OPENKEY links.
        """
        items: list[dict[str, Any]] = [
            self._put_versioned(inc, prev_version, now),
            {"Put": {"TableName": self.table_name, "Item": self._event(inc, event_type, now)}},
        ]
        items += [self._openkey_put(inc.household_id, k, inc.id) for k in new_keys or []]
        if inc.status == "resolved":
            items += [
                {
                    "Delete": {
                        "TableName": self.table_name,
                        "Key": {
                            "PK": keys.household_pk(inc.household_id),
                            "SK": keys.openkey_sk(k),
                        },
                    }
                }
                for k in inc.keys
            ]
        self._client.transact_write_items(TransactItems=items)

    def merge_incidents(
        self,
        into: Incident,
        into_prev_version: int,
        merged: Incident,
        merged_prev_version: int,
        now: datetime,
    ) -> None:
        """One transaction: `into` absorbs `merged`, whose OPENKEYs are re-pointed to `into`."""
        items: list[dict[str, Any]] = [
            self._put_versioned(into, into_prev_version, now),
            self._put_versioned(merged, merged_prev_version, now),
            {"Put": {"TableName": self.table_name, "Item": self._event(into, "merged_in", now)}},
            {"Put": {"TableName": self.table_name, "Item": self._event(merged, "merged", now)}},
        ]
        items += [self._openkey_put(into.household_id, k, into.id) for k in merged.keys]
        self._client.transact_write_items(TransactItems=items)

    def save_summary(self, incident_id: str, content_hash: str, fields: dict[str, Any]) -> bool:
        """Write the triage agent's summary if the incident's content hasn't changed since."""
        names = {f"#{k}": k for k in fields}
        values = {
            f":{k}": v for k, v in json.loads(json.dumps(fields), parse_float=Decimal).items()
        }
        try:
            self.table.update_item(
                Key={"PK": keys.incident_pk(incident_id), "SK": keys.META},
                UpdateExpression="SET "
                + ", ".join(f"#{k} = :{k}" for k in fields)
                + ", #version = #version + :one",
                ConditionExpression="content_hash = :h",
                ExpressionAttributeNames=names | {"#version": "version"},
                ExpressionAttributeValues=values | {":h": content_hash, ":one": 1},
            )
        except self._client.exceptions.ConditionalCheckFailedException:
            return False
        return True

    @staticmethod
    def _event(inc: Incident, event_type: str, now: datetime) -> dict[str, Any]:
        at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        latest = inc.signals[-1].external_id if inc.signals else None
        return {
            "PK": keys.incident_pk(inc.id),
            "SK": keys.event_sk(at, new_id("evt")),
            "entity": "incident_event",
            "type": event_type,
            "at": at,
            "signal_external_id": latest,
        }
