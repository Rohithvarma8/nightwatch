"""Config from env vars, read once at init."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    table_name: str
    bus_name: str
    household_ids: list[str]
    nws_user_agent: str


def load() -> Settings:
    return Settings(
        table_name=os.environ["NIGHTWATCH_TABLE"],
        bus_name=os.environ.get("NIGHTWATCH_BUS", "nightwatch"),
        household_ids=[h for h in os.environ.get("HOUSEHOLD_IDS", "").split(",") if h],
        nws_user_agent=os.environ.get("NWS_USER_AGENT", ""),
    )
