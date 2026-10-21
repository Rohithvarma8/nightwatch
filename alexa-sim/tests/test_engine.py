from types import SimpleNamespace
from typing import Any

import pytest

from nightwatch_sim.engine import (
    BLOCKED_MESSAGE,
    ToolCall,
    Turn,
    TurnRecorder,
    call_tool_result,
    is_affirmative,
    spoken,
    ui_resource_uri,
)

URI = "ui://nightwatch/incidents.html"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("yes", True),
        ("Yes.", True),
        ("yeah, do it", True),
        ("ok", True),
        ("go ahead", True),
        ("  Sure thing", True),
        ("no", False),
        ("roll it back", False),
        ("yesterday's deploy", False),
        ("not yes", False),
        ("tell my roommate", False),
    ],
)
def test_is_affirmative(text: str, expected: bool) -> None:
    assert is_affirmative(text) is expected


def test_spoken_strips_markdown() -> None:
    assert spoken("**Two things.**\n- A *red flag* warning\n- `checkout`") == (
        "Two things. A red flag warning checkout"
    )


def test_ui_resource_uri() -> None:
    assert ui_resource_uri({"ui": {"resourceUri": URI}}) == URI
    assert ui_resource_uri({"ui": {}}) is None
    assert ui_resource_uri(None) is None


def test_call_tool_result_shape() -> None:
    result = {
        "status": "success",
        "toolUseId": "t1",
        "content": [{"text": "One thing."}, {"json": {"x": 1}}],
        "structuredContent": {"incidents": []},
        "metadata": {"ui": {"resourceUri": URI}},
    }
    assert call_tool_result(result) == {
        "content": [{"type": "text", "text": "One thing."}],
        "structuredContent": {"incidents": []},
        "_meta": {"ui": {"resourceUri": URI}},
    }


def _events(name: str, result: dict[str, Any]) -> tuple[SimpleNamespace, SimpleNamespace]:
    use = {"toolUseId": "t1", "name": name, "input": {"incident": "the deploy"}}
    return (
        SimpleNamespace(tool_use=use, cancel_tool=False),
        SimpleNamespace(tool_use=use, result=result),
    )


def test_recorder_holds_confirm_tools_without_yes() -> None:
    rec = TurnRecorder("roll it back", {})
    before, after = _events(
        "rollback_deploy", {"status": "error", "content": [{"text": BLOCKED_MESSAGE}]}
    )
    rec.before(before)  # type: ignore[arg-type]
    rec.after(after)  # type: ignore[arg-type]
    assert before.cancel_tool == BLOCKED_MESSAGE
    assert rec.calls[0].status == "blocked" and rec.calls[0].result is None


def test_recorder_allows_confirm_tools_after_yes() -> None:
    rec = TurnRecorder("yes", {})
    before, after = _events("rollback_deploy", {"status": "success", "content": [{"text": "ok"}]})
    rec.before(before)  # type: ignore[arg-type]
    rec.after(after)  # type: ignore[arg-type]
    assert before.cancel_tool is False
    assert rec.calls[0].status == "ok"


def test_recorder_never_holds_read_or_acknowledge() -> None:
    for name in ("get_active_incidents", "acknowledge"):
        rec = TurnRecorder("what's going on", {"get_active_incidents": URI})
        before, after = _events(name, {"status": "success", "content": [{"text": "ok"}]})
        rec.before(before)  # type: ignore[arg-type]
        rec.after(after)  # type: ignore[arg-type]
        assert before.cancel_tool is False
        assert rec.calls[0].resource_uri == (URI if name == "get_active_incidents" else None)


def test_turn_card_is_last_ui_result() -> None:
    first = ToolCall("get_active_incidents", {}, 150, "ok", URI, {"content": [], "n": 1})
    second = ToolCall("explain_incident", {"incident": "x"}, 160, "ok", URI, {"n": 2})
    third = ToolCall("acknowledge", {}, 170, "ok", None, {"content": []})
    turn = Turn(reply="ok", model="m", total_ms=1, tools=[first, second, third])
    assert turn.card == {"uri": URI, "arguments": {"incident": "x"}, "result": second.result}
    assert "result" not in turn.to_json()["tools"][0]
