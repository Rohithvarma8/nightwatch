"""Incident builder against moto: grouping, fire-risk join/merge, sweep, cancel, replay."""

from datetime import timedelta
from pathlib import Path

from nightwatch_core.timefmt import parse_utc
from nightwatch_pipeline.incidents.handler import process_signal, sweep
from nightwatch_pipeline.ingest.nws import normalize
from nightwatch_pipeline.replay import replay, time_shift
from nightwatch_pipeline.seed import DEMO_HOUSEHOLD

from .conftest import FIXTURES, NOW, RecordingBus, load


def _signal(store, name: str, **kw):
    """Normalize + claim (the builder reads full signals back from the SIG item)."""
    s = normalize(load(name), DEMO_HOUSEHOLD, NOW, **kw)
    assert s is not None
    store.claim_signal(s, NOW)
    return s


def test_updates_group_into_one_incident(store) -> None:
    earlier = _signal(store, "red_flag_warning_earlier")
    later = _signal(store, "red_flag_warning_update")
    assert process_signal(store, earlier, NOW)[0] == "created"
    assert process_signal(store, later, NOW)[0] == "updated"
    assert process_signal(store, later, NOW)[0] == "noop"  # redelivery

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
    assert {e.type for e in inc.evidence} == {"nws_alert", "same_hazard_family"}


def test_late_older_message_does_not_override(store) -> None:
    later = _signal(store, "red_flag_warning_update")
    earlier = _signal(store, "red_flag_warning_earlier")
    process_signal(store, later, NOW)
    assert process_signal(store, earlier, NOW)[0] == "updated"
    (inc,) = store.list_active("hh_demo")
    assert inc.ends_at == later.ends_at and len(inc.signals) == 2


def test_wind_joins_existing_fire_incident(store) -> None:
    process_signal(store, _signal(store, "red_flag_warning_update"), NOW)
    outcome, changed = process_signal(store, _signal(store, "wind_advisory_update"), NOW)
    assert outcome == "joined_fire_risk" and len(changed) == 1
    (inc,) = store.list_active("hh_demo")
    assert inc.title == "Fire risk"
    assert inc.related_keys == ["hh_demo#wind#CAZ374"]
    assert "related_hazard" in [e.type for e in inc.evidence]
    # Later wind updates find the fire-risk incident through the wind OPENKEY.
    assert store.get_open_incident("hh_demo", "hh_demo#wind#CAZ374").id == inc.id


def test_wind_first_then_fire_merges(store) -> None:
    process_signal(store, _signal(store, "wind_advisory_update"), NOW)
    outcome, changed = process_signal(store, _signal(store, "red_flag_warning_update"), NOW)
    assert outcome == "created"
    (inc,) = store.list_active("hh_demo")  # wind incident merged and closed
    assert inc.title == "Fire risk"
    assert [e.type for e in inc.evidence][:2] == ["nws_alert", "related_hazard"]
    assert any(i.id == inc.id and i.title == "Fire risk" for i in changed)


def test_sweep_merges_pre_existing_separate_incidents(store, monkeypatch) -> None:
    """Migration path: incidents created before the fire-risk rule get merged by the sweep."""
    from nightwatch_pipeline.incidents import handler

    monkeypatch.setattr(handler, "reconcile", lambda *a, **k: [])
    monkeypatch.setattr(handler.rules, "find_fire_incident_for_wind", lambda *a, **k: None)
    process_signal(store, _signal(store, "red_flag_warning_update"), NOW)
    process_signal(store, _signal(store, "wind_advisory_update"), NOW)
    assert len(store.list_active("hh_demo")) == 2  # Day 3 state: two separate incidents
    monkeypatch.undo()
    resolved, changed = sweep(store, ["hh_demo"], NOW)
    (inc,) = store.list_active("hh_demo")
    assert inc.title == "Fire risk" and resolved == 0 and len(changed) == 1


def test_sweep_resolves_ended_incidents(store) -> None:
    signal = _signal(store, "wind_advisory_update")
    process_signal(store, signal, NOW)
    assert sweep(store, ["hh_demo"], NOW)[0] == 0
    after_end = parse_utc(signal.ends_at) + timedelta(minutes=1)
    assert sweep(store, ["hh_demo"], after_end)[0] == 1
    assert store.list_active("hh_demo") == []
    assert store.get_open_incident("hh_demo", "hh_demo#wind#CAZ374") is None


def test_cancel_resolves(store) -> None:
    process_signal(store, _signal(store, "red_flag_warning_earlier"), NOW)
    cancel = load("red_flag_warning_update")
    cancel["properties"]["messageType"] = "Cancel"
    s = normalize(cancel, DEMO_HOUSEHOLD, NOW)
    assert s is not None
    store.claim_signal(s, NOW)
    assert process_signal(store, s, NOW)[0] == "resolved"
    assert store.list_active("hh_demo") == []


def test_replay_is_separate_and_flagged(store, bus: RecordingBus) -> None:
    process_signal(store, _signal(store, "red_flag_warning_update"), NOW)
    result = replay(Path(FIXTURES / "red_flag_warning_update.json"), store, bus, "hh_demo", NOW)
    assert result["new"] == 1
    (sig,) = bus.published
    assert sig.replay is True and sig.replay_original_time == "2026-10-15T20:16:00Z"
    process_signal(store, sig, NOW)
    live, replayed = sorted(store.list_active("hh_demo"), key=lambda i: i.replay)
    assert live.replay is False
    assert replayed.replay is True and replayed.replay_original_time == "2026-10-15T20:16:00Z"
    assert replayed.correlation_key.endswith("#replay")


def test_time_shift_keeps_durations() -> None:
    from datetime import datetime

    feature = load("red_flag_warning_update")
    shifted, original = time_shift(feature, NOW)
    assert original == "2026-10-15T13:16:00-07:00"

    def span(props):
        return datetime.fromisoformat(props["ends"]) - datetime.fromisoformat(props["sent"])

    assert span(feature["properties"]) == span(shifted["properties"])
    assert datetime.fromisoformat(shifted["properties"]["sent"]) == NOW
