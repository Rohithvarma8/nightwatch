"""Dedupe + publish (moto DynamoDB + EventBridge)."""

from nightwatch_pipeline.ingest.nws import ingest_features
from nightwatch_pipeline.seed import DEMO_HOUSEHOLD

from .conftest import NOW, RecordingBus, load


def test_dedupe_publishes_each_alert_once(store, bus: RecordingBus) -> None:
    features = [load("red_flag_warning_update"), load("wind_advisory_update")]
    first = ingest_features(features, DEMO_HOUSEHOLD, store, bus, NOW)
    second = ingest_features(features, DEMO_HOUSEHOLD, store, bus, NOW)
    assert first == {"seen": 2, "new": 2, "duplicate": 0, "skipped": 0}
    assert second == {"seen": 2, "new": 0, "duplicate": 2, "skipped": 0}
    assert [s.event for s in bus.published] == ["Red Flag Warning", "Wind Advisory"]


def test_dedupe_item_has_7_day_ttl(store, bus: RecordingBus) -> None:
    ingest_features([load("red_flag_warning_update")], DEMO_HOUSEHOLD, store, bus, NOW)
    pk = "SIG#nws#urn:oid:2.49.0.1.840.0.25f5385cd20fe2206e48c8b684f2305219788c77.004.1"
    item = store.table.get_item(Key={"PK": pk, "SK": "META"})["Item"]
    assert int(item["expires_at"]) - int(NOW.timestamp()) == 7 * 24 * 3600


def test_other_areas_are_skipped(store, bus: RecordingBus) -> None:
    counts = ingest_features([load("heat_advisory_elsewhere")], DEMO_HOUSEHOLD, store, bus, NOW)
    assert counts["skipped"] == 1 and bus.published == []


def test_failed_publish_releases_claim(store, bus: RecordingBus, monkeypatch) -> None:
    feature = load("red_flag_warning_update")
    monkeypatch.setattr(RecordingBus, "publish", lambda self, signals: list(signals))
    try:
        ingest_features([feature], DEMO_HOUSEHOLD, store, bus, NOW)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")
    monkeypatch.undo()
    # Claim was released, so the next run publishes it.
    assert store.claim_signal("nws", feature["properties"]["id"], NOW) is True
