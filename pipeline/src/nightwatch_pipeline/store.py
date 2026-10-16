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
from nightwatch_core.models import Household, Incident

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

    # --- signal dedupe -----------------------------------------------------
    def claim_signal(self, source: str, external_id: str, now: datetime) -> bool:
        """Conditional put on SIG#<source>#<id>. False if this signal was already seen."""
        try:
            self.table.put_item(
                Item={
                    "PK": keys.signal_pk(source, external_id),
                    "SK": keys.META,
                    "entity": "signal",
                    "first_seen_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "expires_at": int((now + SIGNAL_TTL).timestamp()),
                },
                ConditionExpression="attribute_not_exists(PK)",
            )
        except self._client.exceptions.ConditionalCheckFailedException:
            return False
        return True

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

    def update_incident(
        self, inc: Incident, prev_version: int, event_type: str, now: datetime
    ) -> None:
        """Replace the incident if nobody else wrote it since `prev_version`.

        Resolving drops the GSI1 attributes (leaves the active index) and the OPENKEY link.
        """
        items: list[dict[str, Any]] = [
            {
                "Put": {
                    "TableName": self.table_name,
                    "Item": incident_item(inc, now),
                    "ConditionExpression": "version = :v",
                    "ExpressionAttributeValues": {":v": prev_version},
                }
            },
            {"Put": {"TableName": self.table_name, "Item": self._event(inc, event_type, now)}},
        ]
        if inc.status == "resolved":
            items.append(
                {
                    "Delete": {
                        "TableName": self.table_name,
                        "Key": {
                            "PK": keys.household_pk(inc.household_id),
                            "SK": keys.openkey_sk(inc.correlation_key),
                        },
                    }
                }
            )
        self._client.transact_write_items(TransactItems=items)

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
