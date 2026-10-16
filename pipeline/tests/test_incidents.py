"""Incident grouping (OPENKEY), GSI1 membership, expiry sweep, replay."""

from datetime import timedelta
from pathlib import Path

from nightwatch_core.timefmt import parse_utc
from nightwatch_pipeline.incidents.handler import process_signal, sweep
from nightwatch_pipeline.ingest.nws import normalize
from nightwatch_pipeline.replay import replay, time_shift
from nightwatch_pipeline.seed import DEMO_HOUSEHOLD

from .conftest import FIXTURES, NOW, RecordingBus, load


def _signal(name: str, **kw):
    s = normalize(load(name), DEMO_HOUSEHOLD, NOW, **kw)
    assert s is not None
    return s


def test_updates_group_into_one_incident(store) -> None:
    earlier = _signal("red_flag_warning_earlier")
    later = _signal("red_flag_warning_update")
    assert process_signal(store, earlier, NOW) == "created"
    assert process_signal(store, later, NOW) == "updated"
    assert process_signal(store, later, NOW) == "noop"  # redelivery

    (inc,) = store.list_active("hh_demo")
    assert inc.title == "Red Flag Warning" and inc.severity == "high" and inc.status == "open"
    assert [r.external_id for r in inc.signals] == [earlier.external_id, later.external_id]
    assert inc.ends_at == later.ends_at
    assert inc.version == 1
    assert inc.correlation_key == "hh_demo#fire_weather#CAZ374"
    assert inc.spoken_summary == (
        "The National Weather Service has a Red Flag Warning for Southeastern Ventura County "
        "Valleys until 8 PM Saturday."
    )
    assert inc.top_action == "Avoid anything that could spark a fire"
    assert len(inc.spoken_summary.split()) <= 40
    assert {e.type for e in inc.evidence} == {"nws_alert", "same_hazard_family"}


def test_late_older_message_does_not_override(store) -> None:
    later = _signal("red_flag_warning_update")
    earlier = _signal("red_flag_warning_earlier")
    process_signal(store, later, NOW)
    assert process_signal(store, earlier, NOW) == "updated"
    (inc,) = store.list_active("hh_demo")
    assert inc.ends_at == later.ends_at and len(inc.signals) == 2


def test_different_family_is_a_separate_incident(store) -> None:
    process_signal(store, _signal("red_flag_warning_update"), NOW)
    process_signal(store, _signal("wind_advisory_update"), NOW)
    active = store.list_active("hh_demo")
    assert [i.title for i in active] == ["Red Flag Warning", "Wind Advisory"]  # GSI1: high first


def test_sweep_resolves_ended_incidents(store) -> None:
    signal = _signal("wind_advisory_update")
    process_signal(store, signal, NOW)
    assert sweep(store, ["hh_demo"], NOW) == 0
    after_end = parse_utc(signal.ends_at) + timedelta(minutes=1)
    assert sweep(store, ["hh_demo"], after_end) == 1
    assert store.list_active("hh_demo") == []
    # OPENKEY is gone, so the next wind alert starts a new incident.
    assert store.get_open_incident("hh_demo", "hh_demo#wind#CAZ374") is None


def test_cancel_resolves(store) -> None:
    process_signal(store, _signal("red_flag_warning_earlier"), NOW)
    cancel = load("red_flag_warning_update")
    cancel["properties"]["messageType"] = "Cancel"
    s = normalize(cancel, DEMO_HOUSEHOLD, NOW)
    assert s is not None
    assert process_signal(store, s, NOW) == "resolved"
    assert store.list_active("hh_demo") == []


def test_replay_is_separate_and_flagged(store, bus: RecordingBus) -> None:
    process_signal(store, _signal("red_flag_warning_update"), NOW)
    path = Path(FIXTURES / "red_flag_warning_update.json")
    result = replay(path, store, bus, "hh_demo", NOW)
    assert result["new"] == 1
    (sig,) = bus.published
    assert sig.replay is True and sig.replay_original_time == "2026-10-15T20:16:00Z"
    assert sig.sent_at == "2026-10-15T21:00:00Z"
    process_signal(store, sig, NOW)

    live, replayed = sorted(store.list_active("hh_demo"), key=lambda i: i.replay)
    assert live.replay is False
    assert replayed.replay is True and replayed.replay_original_time == "2026-10-15T20:16:00Z"
    assert replayed.correlation_key.endswith("#replay")
    assert replayed.spoken_summary.startswith("Replay of a real alert.")


def test_time_shift_keeps_durations() -> None:
    feature = load("red_flag_warning_update")
    shifted, original = time_shift(feature, NOW)
    assert original == "2026-10-15T13:16:00-07:00"
    p, q = feature["properties"], shifted["properties"]
    from datetime import datetime

    def span(props):
        return datetime.fromisoformat(props["ends"]) - datetime.fromisoformat(props["sent"])

    assert span(p) == span(q)
    assert datetime.fromisoformat(q["sent"]) == NOW
