"""Publish signals to the EventBridge bus."""

from collections.abc import Sequence

import boto3

from nightwatch_core.models import Signal

DETAIL_TYPE = "Signal"
LIVE_SOURCE = "nightwatch.ingest.{source}"
REPLAY_SOURCE = "nightwatch.replay"
_BATCH = 10  # PutEvents limit


class Bus:
    def __init__(self, bus_name: str) -> None:
        self.bus_name = bus_name
        self._client = boto3.client("events")

    def publish(self, signals: Sequence[Signal]) -> list[Signal]:
        """Put signals on the bus. Returns the ones that failed."""
        failed: list[Signal] = []
        for start in range(0, len(signals), _BATCH):
            batch = signals[start : start + _BATCH]
            resp = self._client.put_events(
                Entries=[
                    {
                        "EventBusName": self.bus_name,
                        "Source": REPLAY_SOURCE
                        if s.replay
                        else LIVE_SOURCE.format(source=s.source),
                        "DetailType": DETAIL_TYPE,
                        "Detail": s.model_dump_json(),
                    }
                    for s in batch
                ]
            )
            for signal, entry in zip(batch, resp["Entries"], strict=True):
                if "ErrorCode" in entry:
                    failed.append(signal)
        return failed
