"""Active incidents from the single table: GSI1 Query + household profile GetItem."""

import time
from datetime import datetime
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.config import Config

from nightwatch_core import keys
from nightwatch_core.models import Incident

# Fail fast: the whole Alexa round trip has 500 ms.
_BOTO_CONFIG = Config(connect_timeout=1, read_timeout=1, retries={"max_attempts": 2})
_QUERY_LIMIT = 20
_NAME_TTL_S = 300


class DynamoIncidentSource:
    def __init__(self, table_name: str, household_id: str) -> None:
        resource: Any = boto3.resource("dynamodb", config=_BOTO_CONFIG)  # untyped
        self._table = resource.Table(table_name)
        self._household_id = household_id
        self._name: tuple[float, str] | None = None

    def household_name(self) -> str:
        """Profile name, cached for 5 minutes per container."""
        if self._name and time.monotonic() - self._name[0] < _NAME_TTL_S:
            return self._name[1]
        item = self._table.get_item(
            Key={"PK": keys.household_pk(self._household_id), "SK": keys.PROFILE},
            ProjectionExpression="#n",
            ExpressionAttributeNames={"#n": "name"},
        ).get("Item")
        name = str(item["name"]) if item else "your household"
        self._name = (time.monotonic(), name)
        return name

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
