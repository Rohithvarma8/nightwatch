"""Correlation rules (pure): fire-risk pairing, derivation, merge plan."""

from datetime import timedelta

from nightwatch_core.models import Incident, Signal
from nightwatch_core.timefmt import to_utc_iso
from nightwatch_pipeline.ingest.nws import normalize
from nightwatch_pipeline.seed import DEMO_HOUSEHOLD
from nightwatch_pipeline.triage import rules, templates

from .conftest import NOW, load


def sig(name: str, **update) -> Signal:
    s = normalize(load(name), DEMO_HOUSEHOLD, NOW)
    assert s is not None
    return s.model_copy(update=update)


def test_red_flag_and_wind_same_zone_overlapping_pair() -> None:
    fire, wind = sig("red_flag_warning_update"), sig("wind_advisory_update")
    assert rules.is_fire_risk_pair(fire, wind)


def test_no_pair_across_zones() -> None:
    fire, wind = sig("red_flag_warning_update"), sig("wind_advisory_update", area="CAZ999")
    assert not rules.is_fire_risk_pair(fire, wind)


def test_no_pair_without_overlap() -> None:
    fire = sig("red_flag_warning_update")  # onset Oct 15 20:16Z
    wind = sig(
        "wind_advisory_update", onset_at="2026-10-14T00:00:00Z", ends_at="2026-10-15T20:00:00Z"
    )
    assert not rules.is_fire_risk_pair(fire, wind)


def test_no_pair_between_live_and_replay() -> None:
    fire, wind = sig("red_flag_warning_update"), sig("wind_advisory_update", replay=True)
    assert not rules.is_fire_risk_pair(fire, wind)


def test_no_pair_for_other_families() -> None:
    fire = sig("red_flag_warning_update")
    heat = sig("wind_advisory_update", event="Heat Advisory", hazard_family="heat")
    assert not rules.is_fire_risk_pair(fire, heat)


def test_derive_fire_risk() -> None:
    fire, wind = sig("red_flag_warning_update"), sig("wind_advisory_update")
    d = rules.derive([fire, wind], NOW)
    assert d.title == "Fire risk" and d.severity == "high" and d.status == "open"
    assert d.primary is fire and d.supporting is wind
    types = [e.type for e in d.evidence]
    assert types == ["nws_alert", "related_hazard", "nws_alert"]
    related = d.evidence[1]
    assert related.detail == "Wind Advisory in the same zone during the Red Flag Warning window"
    assert {r.role for r in d.refs if r.event == "Wind Advisory"} == {"supporting"}
    assert d.ends_at == fire.ends_at  # the later of the two


def test_derive_falls_back_to_wind_when_fire_ends() -> None:
    fire, wind = sig("red_flag_warning_update"), sig("wind_advisory_update")
    fire = fire.model_copy(update={"ends_at": to_utc_iso(NOW + timedelta(minutes=30))})
    d = rules.derive([fire, wind], NOW + timedelta(hours=1))
    assert d.title == "Wind Advisory" and d.supporting is None and d.status == "open"


def test_derive_resolves_when_everything_ended() -> None:
    wind = sig("wind_advisory_update")
    assert rules.derive([wind], NOW + timedelta(days=3)).status == "resolved"


def test_content_hash_ignores_time_but_tracks_members() -> None:
    fire, wind = sig("red_flag_warning_update"), sig("wind_advisory_update")
    a = rules.derive([fire], NOW).content_hash
    assert a == rules.derive([fire], NOW + timedelta(minutes=5)).content_hash
    assert a != rules.derive([fire, wind], NOW).content_hash


def _incident(signals: list[Signal]) -> Incident:
    first = signals[0]
    shell = Incident(
        id=f"inc_{first.event.replace(' ', '')}",
        household_id="hh_demo",
        kind="hazard",
        title=first.event,
        severity=first.severity,
        status="open",
        started_at=first.sent_at,
        updated_at=first.sent_at,
        ends_at=first.ends_at,
        correlation_key=rules.correlation_key(first),
        spoken_summary="",
        detail_summary="",
        summarizer=templates.summarizer(),
    )
    return rules.apply_derived(shell, signals, DEMO_HOUSEHOLD, NOW)


def test_merge_plan_pairs_standalone_wind_with_fire() -> None:
    fire, wind = sig("red_flag_warning_update"), sig("wind_advisory_update")
    f_inc, w_inc = _incident([fire]), _incident([wind])
    plan = rules.merge_plan([(f_inc, [fire]), (w_inc, [wind])], NOW)
    assert [(a.id, b.id) for a, b in plan] == [(f_inc.id, w_inc.id)]


def test_merge_plan_skips_other_zones() -> None:
    fire, wind = sig("red_flag_warning_update"), sig("wind_advisory_update", area="CAZ999")
    assert rules.merge_plan([(_incident([fire]), [fire]), (_incident([wind]), [wind])], NOW) == []


def test_fire_risk_template_is_short_and_grounded_in_names() -> None:
    fire, wind = sig("red_flag_warning_update"), sig("wind_advisory_update")
    text = templates.spoken_summary(fire, wind, DEMO_HOUSEHOLD, NOW)
    assert text == (
        "The National Weather Service has a Red Flag Warning for Southeastern Ventura County "
        "Valleys until 8 PM Saturday, and a Wind Advisory until 8 PM Friday."
    )
    assert len(text.split()) <= 40
