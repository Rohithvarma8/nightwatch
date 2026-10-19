"""SNS publish: the one outbound call allowed in the request path (2 s timeout, no retries)."""

import json
from typing import Any

import boto3
from botocore.config import Config


class SnsNotifier:
    def __init__(self, topic_arn: str) -> None:
        self._topic_arn = topic_arn
        self._client = boto3.client(
            "sns", config=Config(connect_timeout=1, read_timeout=2, retries={"max_attempts": 1})
        )

    def publish(self, msg: dict[str, Any]) -> str:
        return self._client.publish(TopicArn=self._topic_arn, Message=json.dumps(msg))["MessageId"]
