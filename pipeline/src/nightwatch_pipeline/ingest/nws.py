"""NWS ingester: alerts/active?point=<lat>,<lon> → Signal → dedupe → bus.

Lambda handler runs every 5 minutes (EventBridge Scheduler). Replay reuses `ingest_features`.
"""

import json
import urllib.request
from datetime import UTC, datetime
from functools import cache
from typing import Any

from aws_lambda_powertools import Logger

from nightwatch_core.hazards import hazard_family, nws_severity
from nightwatch_core.ids import new_id
from nightwatch_core.models import Household, Signal
from nightwatch_core.timefmt import to_utc_iso
from nightwatch_pipeline import settings as settings_mod
from nightwatch_pipeline.bus import Bus
from nightwatch_pipeline.store import Store

logger = Logger(service="nightwatch-ingest-nws")

ALERTS_URL = "https://api.weather.gov/alerts/active?point={lat},{lon}"
SOURCE = "nws"


def fetch_active(lat: float, lon: float, user_agent: str, timeout: float = 10) -> list[dict]:
    req = urllib.request.Request(
        ALERTS_URL.format(lat=f"{lat:.4f}", lon=f"{lon:.4f}"),
        headers={"User-Agent": user_agent, "Accept": "application/geo+json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https URL)
        return json.load(resp).get("features", [])


def normalize(
    feature: dict[str, Any],
    household: Household,
    observed_at: datetime,
    *,
    external_id: str | None = None,
    replay: bool = False,
    replay_original_time: str | None = None,
) -> Signal | None:
    """One NWS alert feature → Signal, or None if it isn't for this household."""
    p = feature["properties"]
    if p.get("status") != "Actual":
        return None
    ugc = set(p.get("geocode", {}).get("UGC", []))
    zone = next((z for z in (household.fire_zone, household.forecast_zone) if z.id in ugc), None)
    if zone is None:
        return None
    area_desc = p.get("areaDesc", "")
    event = p["event"]
    return Signal(
        id=new_id("sig"),
        household_id=household.id,
        source=SOURCE,
        external_id=external_id or p["id"],
        event=event,
        hazard_family=hazard_family(event),
        severity=nws_severity(event, p["severity"], p["urgency"], p["certainty"]),
        area=zone.id,
        # Spoken text may only use place names that appear in the source alert.
        area_name=zone.name if zone.name in area_desc else area_desc.split(";")[0].strip(),
        headline=p.get("headline") or event,
        sender_name=p.get("senderName", "National Weather Service"),
        message_type=p["messageType"],
        sent_at=to_utc_iso(p["sent"]),
        onset_at=to_utc_iso(p["onset"]) if p.get("onset") else None,
        ends_at=to_utc_iso(p.get("ends") or p["expires"]),
        observed_at=to_utc_iso(observed_at),
        url=p.get("@id") or feature.get("id", ""),
        nws_severity=p["severity"],
        nws_urgency=p["urgency"],
        nws_certainty=p["certainty"],
        references=[r["identifier"] for r in p.get("references", [])],
        replay=replay,
        replay_original_time=replay_original_time,
    )


def ingest_features(
    features: list[dict[str, Any]],
    household: Household,
    store: Store,
    bus: Bus,
    now: datetime,
    **normalize_kwargs: Any,
) -> dict[str, int]:
    """Normalize, dedupe (conditional put), publish new signals. Same path for live and replay."""
    counts = {"seen": len(features), "new": 0, "duplicate": 0, "skipped": 0}
    fresh: list[Signal] = []
    for feature in features:
        signal = normalize(feature, household, now, **normalize_kwargs)
        if signal is None:
            counts["skipped"] += 1
        elif store.claim_signal(SOURCE, signal.external_id, now):
            fresh.append(signal)
        else:
            counts["duplicate"] += 1
    failed = bus.publish(fresh)
    for signal in failed:
        store.release_signal(SOURCE, signal.external_id)
    if failed:
        raise RuntimeError(f"PutEvents failed for {len(failed)} signal(s); claims released")
    counts["new"] = len(fresh)
    return counts


@cache
def _deps() -> tuple[settings_mod.Settings, Store, Bus]:
    """Config + clients once per container."""
    cfg = settings_mod.load()
    return cfg, Store(cfg.table_name), Bus(cfg.bus_name)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    cfg, store, bus = _deps()
    now = datetime.now(UTC)
    results: dict[str, Any] = {}
    errors = 0
    for household_id in cfg.household_ids:
        household = store.get_household(household_id)
        if household is None:
            logger.warning("household not found", extra={"household_id": household_id})
            continue
        try:
            features = fetch_active(household.lat, household.lon, cfg.nws_user_agent)
            results[household_id] = ingest_features(features, household, store, bus, now)
        except Exception:
            errors += 1
            logger.exception("nws ingest failed", extra={"household_id": household_id})
    logger.info("nws ingest done", extra={"results": results, "errors": errors})
    if errors:
        raise RuntimeError(f"NWS ingest failed for {errors} household(s)")
    return results
