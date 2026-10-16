"""NWS normalizer against real archived alerts (fixtures copied from nightwatch-alert-archive)."""

from nightwatch_pipeline.ingest.nws import normalize
from nightwatch_pipeline.seed import DEMO_HOUSEHOLD

from .conftest import NOW, load


def test_red_flag_warning() -> None:
    s = normalize(load("red_flag_warning_update"), DEMO_HOUSEHOLD, NOW)
    assert s is not None
    assert s.source == "nws"
    assert s.external_id == "urn:oid:2.49.0.1.840.0.25f5385cd20fe2206e48c8b684f2305219788c77.004.1"
    assert s.event == "Red Flag Warning"
    assert s.hazard_family == "fire_weather"
    assert s.severity == "high"
    assert (s.area, s.area_name) == ("CAZ374", "Southeastern Ventura County Valleys")
    assert s.message_type == "Update"
    assert s.sent_at == "2026-10-15T20:16:00Z"  # 13:16 PDT
    assert s.ends_at == "2026-10-18T03:00:00Z"  # `ends` (Oct 17 20:00 PDT), not `expires`
    assert s.sender_name == "NWS Los Angeles/Oxnard CA"
    assert s.url.startswith("https://api.weather.gov/alerts/urn:oid:")
    assert len(s.references) >= 1
    assert s.replay is False and s.replay_original_time is None
    assert s.id.startswith("sig_")


def test_wind_advisory() -> None:
    s = normalize(load("wind_advisory_update"), DEMO_HOUSEHOLD, NOW)
    assert s is not None
    assert (s.event, s.hazard_family, s.severity) == ("Wind Advisory", "wind", "moderate")
    assert s.area == "CAZ374"


def test_alert_for_another_area_is_skipped() -> None:
    assert normalize(load("heat_advisory_elsewhere"), DEMO_HOUSEHOLD, NOW) is None


def test_non_actual_status_is_skipped() -> None:
    feature = load("red_flag_warning_update")
    feature["properties"]["status"] = "Test"
    assert normalize(feature, DEMO_HOUSEHOLD, NOW) is None


def test_ends_falls_back_to_expires() -> None:
    feature = load("red_flag_warning_update")
    feature["properties"]["ends"] = None
    s = normalize(feature, DEMO_HOUSEHOLD, NOW)
    assert s is not None and s.ends_at == "2026-10-17T02:30:00Z"  # expires Oct 16 19:30 PDT
