"""Single-table access for the tools: GSI1 Query, GetItem, and UpdateItem (INC#*, RATE#*).

Household profile, contacts, and policy are cached per container (5 minutes).
"""

import time
from datetime import datetime, timedelta
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.config import Config

from nightwatch_core import keys
from nightwatch_core.ids import new_id
from nightwatch_core.models import Contact, EscalationPolicy, Incident

# Fail fast: the whole Alexa round trip has 500 ms.
_BOTO_CONFIG = Config(connect_timeout=1, read_timeout=1, retries={"max_attempts": 2})
_QUERY_LIMIT = 20
_NAME_TTL_S = 300
_RATE_TTL = timedelta(hours=2)


def _iso(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


class DynamoIncidentSource:
    def __init__(self, table_name: str, household_id: str) -> None:
        resource: Any = boto3.resource("dynamodb", config=_BOTO_CONFIG)  # untyped
        self._table = resource.Table(table_name)
        self._household_id = household_id
        self._client = self._table.meta.client
        self._cache: dict[str, tuple[float, Any]] = {}

    def _cached(self, key: str, load: Any) -> Any:
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < _NAME_TTL_S:
            return hit[1]
        value = load()
        self._cache[key] = (time.monotonic(), value)
        return value

    def _profile(self) -> dict[str, Any]:
        def load() -> dict[str, Any]:
            item = self._table.get_item(
                Key={"PK": keys.household_pk(self._household_id), "SK": keys.PROFILE},
                ProjectionExpression="#n, tz",
                ExpressionAttributeNames={"#n": "name"},
            ).get("Item")
            return item or {}

        return self._cached("profile", load)

    def household_name(self) -> str:
        return str(self._profile().get("name") or "your household")

    def household_tz(self) -> str:
        return str(self._profile().get("tz") or "UTC")

    def contacts(self) -> list[Contact]:
        def load() -> list[Contact]:
            items = self._table.query(
                KeyConditionExpression=Key("PK").eq(keys.household_pk(self._household_id))
                & Key("SK").begins_with(keys.CONTACT_PREFIX)
            ).get("Items", [])
            return [Contact.model_validate(i) for i in items]

        return self._cached("contacts", load)

    def escalation_policy(self) -> EscalationPolicy | None:
        def load() -> EscalationPolicy | None:
            item = self._table.get_item(
                Key={"PK": keys.household_pk(self._household_id), "SK": keys.ESCALATION_POLICY}
            ).get("Item")
            return EscalationPolicy.model_validate(item) if item else None

        return self._cached("policy", load)

    def _update_status(
        self, incident_id: str, update: str, condition: str, values: dict[str, Any]
    ) -> Incident | None:
        try:
            item = self._table.update_item(
                Key={"PK": keys.incident_pk(incident_id), "SK": keys.META},
                UpdateExpression=update + ", #v = #v + :one",
                ConditionExpression="attribute_exists(PK) AND household_id = :hh AND " + condition,
                ExpressionAttributeNames={"#s": "status", "#v": "version"},
                ExpressionAttributeValues=values | {":one": 1, ":hh": self._household_id},
                ReturnValues="ALL_NEW",
            )["Attributes"]
        except self._client.exceptions.ConditionalCheckFailedException:
            return None
        return Incident.model_validate(item)

    def acknowledge(self, incident_id: str, now: datetime) -> tuple[Incident | None, bool]:
        updated = self._update_status(
            incident_id,
            "SET #s = :ack, acked_at = :at, acked_by = :by, updated_at = :at",
            "#s IN (:open, :esc)",
            {":ack": "acknowledged", ":open": "open", ":esc": "escalated", ":at": _iso(now),
             ":by": "voice"},
        )  # fmt: skip
        if updated is not None:
            return updated, True
        return self.get_incident(incident_id), False  # already acknowledged, or resolved

    def mark_escalated(self, incident_id: str, now: datetime) -> Incident | None:
        return self._update_status(
            incident_id,
            "SET #s = :esc, escalated_at = :at, updated_at = :at",
            "#s <> :resolved",
            {":esc": "escalated", ":resolved": "resolved", ":at": _iso(now)},
        )

    def take_notify_slot(self, contact_id: str, now: datetime, limit: int) -> bool:
        """Atomic counter per contact per clock hour (fixed window)."""
        try:
            self._table.update_item(
                Key={
                    "PK": keys.rate_pk(self._household_id, contact_id),
                    "SK": now.strftime("%Y-%m-%dT%H"),
                },
                UpdateExpression="SET expires_at = :ttl ADD #c :one",
                ConditionExpression="attribute_not_exists(#c) OR #c < :limit",
                ExpressionAttributeNames={"#c": "count"},
                ExpressionAttributeValues={
                    ":one": 1,
                    ":limit": limit,
                    ":ttl": int((now + _RATE_TTL).timestamp()),
                },  # fmt: skip
            )
        except self._client.exceptions.ConditionalCheckFailedException:
            return False
        return True

    def add_event(self, incident_id: str, event_type: str, now: datetime, **detail: str) -> None:
        """Timeline item via UpdateItem (creates it): the role has UpdateItem on INC#* only."""
        fields = {"entity": "incident_event", "type": event_type, "at": _iso(now), **detail}
        self._table.update_item(
            Key={
                "PK": keys.incident_pk(incident_id),
                "SK": keys.event_sk(_iso(now), new_id("evt")),
            },
            UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in fields),
            ExpressionAttributeNames={f"#{k}": k for k in fields},
            ExpressionAttributeValues={f":{k}": v for k, v in fields.items()},
        )

    def active_incidents(self, now: datetime) -> list[Incident]:
        resp = self._table.query(
            IndexName=keys.GSI1,
            KeyConditionExpression=Key("GSI1PK").eq(keys.active_gsi1_pk(self._household_id)),
            Limit=_QUERY_LIMIT,
        )
        return [Incident.model_validate(i) for i in resp.get("Items", [])]

    def get_incident(self, incident_id: str) -> Incident | None:
        item = self._table.get_item(Key={"PK": keys.incident_pk(incident_id), "SK": keys.META}).get(
            "Item"
        )
        if not item or item.get("household_id") != self._household_id:
            return None
        return Incident.model_validate(item)
