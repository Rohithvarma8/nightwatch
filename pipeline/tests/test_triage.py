"""Triage agent + Lambda with Bedrock mocked (the `invoke` hook)."""

import json

from nightwatch_pipeline.incidents.handler import process_signal
from nightwatch_pipeline.ingest.nws import normalize
from nightwatch_pipeline.seed import DEMO_HOUSEHOLD
from nightwatch_pipeline.triage import agent
from nightwatch_pipeline.triage.handler import run

from .conftest import NOW, load

NOVA, HAIKU = "amazon.nova-lite-v1:0", "us.anthropic.claude-haiku-4-5-20251001-v1:0"

GOOD = {
    "spoken_summary": "A Red Flag Warning covers Southeastern Ventura County Valleys until "
    "8 PM Saturday, with Santa Ana winds and very dry air.",
    "detail_summary": "Strong Santa Ana winds and low humidity mean any new fire could grow fast.",
    "recommended_actions": ["Avoid anything that could spark a fire", "Be ready to evacuate"],
}
INVENTED = GOOD | {"spoken_summary": "Winds could gust to 75 mph in Simi Valley tonight."}


def fake_invoke(replies: dict[str, object]):
    calls: list[str] = []

    def invoke(model_id: str, system: str, prompt: str, timeout_s: float) -> str:
        calls.append(model_id)
        assert "JSON" in system and "<<<" in prompt and timeout_s <= agent.BUDGET_S
        reply = replies[model_id]
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else f"Here you go:\n{json.dumps(reply)}"

    invoke.calls = calls  # type: ignore[attr-defined]
    return invoke


def _incident(store):
    s = normalize(load("red_flag_warning_update"), DEMO_HOUSEHOLD, NOW)
    assert s is not None
    store.claim_signal(s, NOW)
    process_signal(store, s, NOW)
    (inc,) = store.list_active("hh_demo")
    return inc


def test_primary_model_grounded_output_is_saved(store) -> None:
    inc = _incident(store)
    invoke = fake_invoke({NOVA: GOOD, HAIKU: AssertionError("should not be called")})
    assert run(store, inc.id, inc.content_hash, [NOVA, HAIKU], invoke)["outcome"] == "summarized"
    saved = store.get_incident(inc.id)
    assert saved.spoken_summary == GOOD["spoken_summary"]
    assert saved.recommended_actions == GOOD["recommended_actions"]
    assert saved.summarizer.model == NOVA
    assert saved.summarizer.fallback_used is False and saved.summarizer.grounding_passed is True
    assert saved.summarizer.content_hash == inc.content_hash
    assert saved.version == inc.version + 1


def test_invented_number_is_rejected_then_fallback_model_used(store) -> None:
    inc = _incident(store)
    invoke = fake_invoke({NOVA: INVENTED, HAIKU: GOOD})
    assert run(store, inc.id, inc.content_hash, [NOVA, HAIKU], invoke)["outcome"] == "summarized"
    assert invoke.calls == [NOVA, HAIKU]
    assert store.get_incident(inc.id).summarizer.model == HAIKU


def test_all_models_fail_keeps_template(store) -> None:
    inc = _incident(store)
    invoke = fake_invoke({NOVA: TimeoutError("read timeout"), HAIKU: "not json at all"})
    assert run(store, inc.id, inc.content_hash, [NOVA, HAIKU], invoke)["outcome"] == "fallback"
    saved = store.get_incident(inc.id)
    assert saved.spoken_summary == inc.spoken_summary  # template kept
    assert saved.summarizer.fallback_used is True
    assert saved.summarizer.model.startswith("template-v1")


def test_schema_violation_rejected(store) -> None:
    inc = _incident(store)
    too_long = GOOD | {"spoken_summary": " ".join(["word"] * 41)}
    extra = GOOD | {"confidence": "high"}
    for bad in (too_long, extra, GOOD | {"recommended_actions": ["a", "b", "c", "d"]}):
        invoke = fake_invoke({NOVA: bad})
        assert run(store, inc.id, inc.content_hash, [NOVA], invoke)["outcome"] == "fallback"


def test_stale_event_is_skipped(store) -> None:
    inc = _incident(store)
    invoke = fake_invoke({})
    result = run(store, inc.id, "not-the-current-hash", [NOVA], invoke)
    assert result == {"outcome": "skipped", "reason": "stale event"} and invoke.calls == []


def test_budget_stops_further_attempts() -> None:
    ticks = iter([0.0, 0.0, 0.0, 7.0, 7.0])  # first attempt "takes" 7 s of the 8 s budget
    invoke = fake_invoke({NOVA: "garbage", HAIKU: GOOD})
    result = agent.summarize([], [], [NOVA, HAIKU], invoke=invoke, clock=lambda: next(ticks))
    assert invoke.calls == [NOVA] and result.fallback_used
    assert result.attempts[-1] == {"model": HAIKU, "error": "budget exhausted"}
