"""Server config from env vars, read once at init (no per-request lookups)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    table_name: str | None  # unset → fixture incidents (local dev, contract tests)
    household_id: str
    allowed_hosts: str
    notify_topic_arn: str | None  # unset → in-memory notifier (local dev, contract tests)


def load() -> Settings:
    return Settings(
        table_name=os.environ.get("NIGHTWATCH_TABLE") or None,
        household_id=os.environ.get("HOUSEHOLD_ID", "hh_demo"),
        allowed_hosts=os.environ.get("MCP_ALLOWED_HOSTS", ""),
        notify_topic_arn=os.environ.get("NOTIFY_TOPIC_ARN") or None,
    )
