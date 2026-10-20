"""Prod path: normalizer (alarm + CodeDeploy events), deploy-proximity rule, builder, resolution."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from nightwatch_core.models import Signal
from nightwatch_core.timefmt import parse_utc, to_utc_iso
from nightwatch_pipeline.escalation.schedule import EscalationScheduler
from nightwatch_pipeline.incidents.handler import process_signal
from nightwatch_pipeline.ingest.prod import normalize_alarm, normalize_deploy
from nightwatch_pipeline.seed import DEMO_POLICY, demo_contact
from nightwatch_pipeline.triage import rules

from .conftest import NOW

PROD = Path(__file__).parent / "fixtures" / "prod"


def event(name: str) -> dict[str, Any]:
    return json.loads((PROD / f"{name}.json").read_text())


def alarm(name: str = "alarm_alarm") -> Signal:
    s = normalize_alarm(event(name), "hh_demo", NOW)
    assert s is not None
    return s


def deploy(**attrs: str) -> Signal:
    s = normalize_deploy(
        event("deploy_success"),
        event("get_deployment")["deploymentInfo"],
        event("get_deployment_target")["deploymentTarget"]["lambdaTarget"],
        "hh_demo",
        NOW,
    )
    assert s is not None
    return s.model_copy(update=attrs)


# --- normalizer -----------------------------------------------------------------------------


def test_alarm_to_signal() -> None:
    s = alarm()
    assert (s.source, s.kind, s.hazard_family) == ("cloudwatch", "prod", "prod")
    assert s.event == "checkout-service latency" and s.area == "checkout-service"
    assert s.message_type == "Alert" and s.severity == "moderate"
    assert s.sent_at == "2026-10-20T22:06:21Z"
    assert s.external_id == "nightwatch-checkout-latency-p95#2026-10-20T22:06:21.097+0000"
    assert s.attributes == {
        "alarm_name": "nightwatch-checkout-latency-p95", "state": "ALARM", "metric": "Duration",
        "statistic": "p95", "threshold": "500", "period_s": "60",
    }  # fmt: skip
    assert "1008.07" in s.headline and "500.0" in s.headline  # grounding source has the numbers


def test_ok_is_a_cancel_and_insufficient_data_is_ignored() -> None:
    assert alarm("alarm_ok").message_type == "Cancel"
    assert normalize_alarm(event("alarm_insufficient"), "hh_demo", NOW) is None


def test_deploy_success_to_signal_with_versions() -> None:
    d = deploy()
    assert (d.source, d.kind, d.area) == ("codedeploy", "prod", "checkout-service")
    assert d.external_id == "d-3869LHKLL" and d.sent_at == "2026-10-20T22:04:16Z"
    assert d.attributes["from_version"] == "2" and d.attributes["to_version"] == "3"
    assert d.headline == (
        "Deployment d-3869LHKLL of checkout-service from version 2 to 3 succeeded."
    )


def test_real_bad_deploy_is_two_minutes_before_real_alarm() -> None:
    p = rules.deploy_proximity(alarm(), [deploy()])
    assert p is not None and p.minutes == 2


def test_deploy_start_is_ignored() -> None:
    info = event("get_deployment")["deploymentInfo"]
    target = event("get_deployment_target")["deploymentTarget"]["lambdaTarget"]
    assert normalize_deploy(event("deploy_start"), info, target, "hh_demo", NOW) is None


# --- deploy-proximity rule ------------------------------------------------------------------


def _at(s: Signal, minutes_before_alarm: float) -> Signal:
    t = parse_utc(alarm().sent_at) - timedelta(minutes=minutes_before_alarm)
    return s.model_copy(update={"sent_at": to_utc_iso(t), "ends_at": to_utc_iso(t)})


@pytest.mark.parametrize(
    ("minutes_before", "expected"),
    [(3.5, 4), (0.2, 1), (15, 15), (15.5, None), (-1, None)],  # -1: deploy after the alarm
)
def test_proximity_window(minutes_before, expected) -> None:
    p = rules.deploy_proximity(alarm(), [_at(deploy(), minutes_before)])
    assert (p.minutes if p else None) == expected


def test_other_service_deploy_is_not_blamed() -> None:
    other = _at(deploy(area="inventory-service", external_id="d-OTHER"), 2)
    assert rules.deploy_proximity(alarm(), [other]) is None
    p = rules.deploy_proximity(alarm(), [other, _at(deploy(), 4)])
    assert p is not None and p.other_services_changed == ["inventory-service"]
    assert "inventory-service also changed" in rules.proximity_evidence(p).detail


def test_derive_prod_with_proximity() -> None:
    d = rules.derive([alarm(), _at(deploy(), 4)], NOW)
    assert d.title == "checkout-service latency" and d.severity == "high" and d.status == "open"
    ev = {e.type: e for e in d.evidence}
    assert ev["deploy_proximity"].detail == (
        "Latency rose 4 minutes after deployment d-3869LHKLL (v2→v3); no other service changed"
    )
    assert ev["deploy_proximity"].spoken == (
        "Latency rose 4 minutes after a deploy from version 2 to 3"
    )
    assert "d-3869LHKLL" not in (ev["deploy_proximity"].spoken or "")


def test_derive_prod_without_deploy_stays_moderate() -> None:
    d = rules.derive([alarm()], NOW)
    assert d.severity == "moderate" and [e.type for e in d.evidence] == ["alarm"]


# --- builder ----------------------------------------------------------------------------------


def _ingest(store, s: Signal) -> Signal:
    store.claim_signal(s, NOW)
    return s


def test_alarm_after_deploy_makes_high_prod_incident(store, aws) -> None:
    store.put_contact(demo_contact(None))
    store.put_policy(DEMO_POLICY)
    scheduler = EscalationScheduler(
        "arn:aws:lambda:us-west-2:1:function:esc", "arn:aws:iam::1:role/r"
    )
    dep = _ingest(store, _at(deploy(), 4))
    assert process_signal(store, dep, NOW)[0] == "deploy_recorded"
    rec = store.deploys_between("checkout-service", "2026-10-20T21:00:00Z", "2026-10-20T23:00:00Z")
    assert [(r.deployment_id, r.from_version, r.to_version) for r in rec] == [
        ("d-3869LHKLL", "2", "3")
    ]

    outcome, _ = process_signal(
        store, _ingest(store, alarm()), NOW, scheduler, ["checkout-service"]
    )
    assert outcome == "created"
    (inc,) = store.list_active("hh_demo")
    assert inc.kind == "prod" and inc.severity == "high"
    assert inc.top_action == "Roll back the latest deploy"
    assert "deploy_proximity" in [e.type for e in inc.evidence]
    assert inc.spoken_summary == (
        "checkout-service latency rose above its alarm threshold 4 minutes after a deploy from "
        "version 2 to 3."
    )
    assert "d-3869LHKLL" not in inc.spoken_summary
    assert inc.escalation_schedule_name  # high → escalation timer
    assert {r.source for r in inc.signals} == {"cloudwatch", "codedeploy"}


def test_alarm_ok_resolves_prod_incident(store) -> None:
    process_signal(store, _ingest(store, alarm()), NOW)
    assert len(store.list_active("hh_demo")) == 1
    assert process_signal(store, _ingest(store, alarm("alarm_ok")), NOW)[0] == "resolved"
    assert store.list_active("hh_demo") == []
    assert store.get_open_incident("hh_demo", "hh_demo#prod#checkout-service") is None


def test_prod_and_home_hazards_never_merge(store) -> None:
    from nightwatch_pipeline.ingest.nws import normalize
    from nightwatch_pipeline.seed import DEMO_HOUSEHOLD

    from .conftest import load

    rfw = normalize(load("red_flag_warning_update"), DEMO_HOUSEHOLD, NOW)
    assert rfw is not None
    process_signal(store, _ingest(store, rfw), NOW)
    process_signal(store, _ingest(store, alarm()), NOW)
    kinds = sorted(i.kind for i in store.list_active("hh_demo"))
    assert kinds == ["hazard", "prod"]
    prod = next(i for i in store.list_active("hh_demo") if i.kind == "prod")
    assert all(e.type in {"alarm", "deploy_proximity"} for e in prod.evidence)
