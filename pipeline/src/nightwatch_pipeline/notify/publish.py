"""Publish a notification request to the SNS fan-out topic (the notifier Lambda delivers it)."""

import json
from typing import Any, Protocol

import boto3
from botocore.config import Config

from nightwatch_core.messages import wire_message

# Wire format lives in nightwatch_core.messages.wire_message (shared with the MCP server).
message = wire_message


class SupportsPublish(Protocol):
    def publish(self, msg: dict[str, Any]) -> str: ...


class Publisher:
    def __init__(self, topic_arn: str) -> None:
        self.topic_arn = topic_arn
        self._client = boto3.client(
            "sns", config=Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 2})
        )

    def publish(self, msg: dict[str, Any]) -> str:
        return self._client.publish(TopicArn=self.topic_arn, Message=json.dumps(msg))["MessageId"]
