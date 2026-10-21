"""Voice-assistant turns: a Strands agent on Bedrock using the live Night Watch MCP server's tools.

One MCPClient (Streamable HTTP) is shared by every session; each turn builds a fresh Agent from the
session's saved messages, so a failed turn can be retried on the fallback model from the same state.
"""

import copy
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from strands import Agent
from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry
from strands.models.bedrock import BedrockModel
from strands.tools.mcp import MCPClient
from strands.types.content import Messages

from nightwatch_sim.settings import Settings

log = logging.getLogger("nightwatch_sim")

SYSTEM_PROMPT = """\
You are the voice assistant on a smart display in someone's home. This is a simulated \
Alexa+ client. You can use the Night Watch tools, which track home hazards (weather, fire, \
air quality) and production on-call incidents (alarms, deploys) for this household.

How you speak:
- Answer in 1 to 3 short spoken sentences. Plain text only: no markdown, lists, or emoji.
- Never say IDs, URLs, or tool names. Refer to incidents by what they are ("the fire risk").
- Times in tool results are already local; say them as given.

Facts:
- For anything about incidents, hazards, alarms, deploys, runbooks, or contacts, call a tool.
- Only state facts that appear in tool results from this conversation. Never add numbers, \
places, causes, or advice the tools didn't give. If the tools don't say, say you don't know.
- If a tool says an alert is replayed, say it's a replayed alert. Never drop that.
- If a tool fails, say briefly that it didn't work.

Actions that need a yes first: rollback_deploy, notify_contact, escalate.
- Before calling one, ask a short yes-or-no question that names the action and who or what \
it affects, then stop and wait.
- Call it only after the user answers yes in their next message. If they say no, don't.
- Reading information and acknowledge need no confirmation. When one request mixes both, do \
the parts that need no confirmation now and ask about the rest in the same reply.
"""

CONFIRM_TOOLS = frozenset({"rollback_deploy", "notify_contact", "escalate"})
AFFIRMATIVE = re.compile(
    r"^\W*(yes|yeah|yep|yup|sure|ok|okay|confirm(ed)?|correct|affirmative|do it|go ahead|"
    r"please do|please)\b",
    re.IGNORECASE,
)
BLOCKED_MESSAGE = (
    "Not called: this action needs the user's yes first. Ask them a yes-or-no question and wait."
)


def is_affirmative(text: str) -> bool:
    return bool(AFFIRMATIVE.match(text))


def spoken(text: str) -> str:
    """Strip markdown the model sometimes emits anyway; the reply goes to text-to-speech."""
    text = re.sub(r"[*_`#>]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", text).strip()


def ui_resource_uri(meta: Any) -> str | None:
    ui = meta.get("ui") if isinstance(meta, dict) else None
    uri = ui.get("resourceUri") if isinstance(ui, dict) else None
    return uri if isinstance(uri, str) else None


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    latency_ms: int  # client-measured MCP round trip (tools/call request → response)
    status: str  # ok | error | blocked
    resource_uri: str | None = None
    result: dict[str, Any] | None = None  # CallToolResult shape, for the MCP Apps card


@dataclass
class Turn:
    reply: str
    model: str
    total_ms: int
    tools: list[ToolCall] = field(default_factory=list)
    error: str | None = None

    @property
    def card(self) -> dict[str, Any] | None:
        """The last tool result in this turn that references a UI resource."""
        for call in reversed(self.tools):
            if call.resource_uri and call.result and call.status == "ok":
                return {
                    "uri": call.resource_uri,
                    "arguments": call.arguments,
                    "result": call.result,
                }
        return None

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        for call in data["tools"]:
            call.pop("result")
        data["card"] = self.card
        return data


def call_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    """Strands ToolResult → MCP CallToolResult, the payload of the card's tool-result."""
    out: dict[str, Any] = {
        "content": [{"type": "text", "text": c["text"]} for c in result["content"] if "text" in c]
    }
    if "structuredContent" in result:
        out["structuredContent"] = result["structuredContent"]
    if result.get("metadata"):
        out["_meta"] = result["metadata"]
    if result.get("status") == "error":
        out["isError"] = True
    return out


class TurnRecorder(HookProvider):
    """Times each MCP tool call and refuses confirm-first tools unless this turn is a yes."""

    def __init__(self, user_text: str, ui_uris: dict[str, str]) -> None:
        self.allow_confirmed = is_affirmative(user_text)
        self.ui_uris = ui_uris
        self.calls: list[ToolCall] = []
        self._started: dict[str, float] = {}
        self._blocked: set[str] = set()
        self._lock = threading.Lock()

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self.before)
        registry.add_callback(AfterToolCallEvent, self.after)

    def before(self, event: BeforeToolCallEvent) -> None:
        use = event.tool_use
        if use["name"] in CONFIRM_TOOLS and not self.allow_confirmed:
            event.cancel_tool = BLOCKED_MESSAGE
            self._blocked.add(use["toolUseId"])
        self._started[use["toolUseId"]] = time.perf_counter()

    def after(self, event: AfterToolCallEvent) -> None:
        use = event.tool_use
        elapsed = time.perf_counter() - self._started.pop(use["toolUseId"], time.perf_counter())
        result = dict(event.result)
        blocked = use["toolUseId"] in self._blocked
        status = "blocked" if blocked else "error" if result.get("status") == "error" else "ok"
        uri = ui_resource_uri(result.get("metadata")) or self.ui_uris.get(use["name"])
        arguments = use["input"] if isinstance(use["input"], dict) else {}
        call = ToolCall(
            name=use["name"],
            arguments=arguments,
            latency_ms=0 if blocked else round(elapsed * 1000),
            status=status,
            resource_uri=uri,
            result=None if blocked else call_tool_result(result),
        )
        with self._lock:
            self.calls.append(call)


class Engine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mcp = MCPClient(url=settings.mcp_url, application_name="nightwatch-alexa-sim")
        self.mcp.start()
        self.tools = list(self.mcp.list_tools_sync())
        self.ui_uris = {
            t.tool_name: uri for t in self.tools if (uri := ui_resource_uri(t.mcp_tool.meta))
        }
        self.read_only = {
            t.tool_name
            for t in self.tools
            if t.mcp_tool.annotations and t.mcp_tool.annotations.read_only_hint
        }
        self._sessions: dict[str, Messages] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def close(self) -> None:
        self.mcp.stop(None, None, None)

    def reset(self, session_id: str) -> None:
        with self._guard:
            self._sessions.pop(session_id, None)

    def _model(self, model_id: str) -> BedrockModel:
        return BedrockModel(
            model_id=model_id,
            region_name=self.settings.region,
            temperature=0.3,
            max_tokens=self.settings.max_tokens,
        )

    def _run(
        self, model_id: str, history: Messages, text: str
    ) -> tuple[str, Messages, TurnRecorder]:
        recorder = TurnRecorder(text, self.ui_uris)
        agent = Agent(
            model=self._model(model_id),
            system_prompt=SYSTEM_PROMPT,
            tools=list(self.tools),
            messages=copy.deepcopy(history),
            hooks=[recorder],
            callback_handler=None,
        )
        try:
            reply = str(agent(text))
        except Exception as exc:
            raise TurnFailed(exc, recorder) from exc
        return reply, agent.messages, recorder

    def turn(self, session_id: str, text: str) -> Turn:
        with self._guard:
            lock = self._locks.setdefault(session_id, threading.Lock())
        with lock:
            history = self._sessions.get(session_id, [])
            started = time.perf_counter()
            model_id = self.settings.primary_model
            try:
                reply, messages, recorder = self._run(model_id, history, text)
            except TurnFailed as failed:
                log.warning("primary model %s failed: %r", model_id, failed.cause)
                # Retry only if nothing with side effects ran, so a yes is never acted on twice.
                if any(c.name not in self.read_only and c.status == "ok" for c in failed.calls):
                    return Turn(
                        reply="Sorry, something went wrong after that action ran.",
                        model=model_id,
                        total_ms=round((time.perf_counter() - started) * 1000),
                        tools=failed.calls,
                        error=repr(failed.cause),
                    )
                model_id = self.settings.fallback_model
                try:
                    reply, messages, recorder = self._run(model_id, history, text)
                except TurnFailed as again:
                    return Turn(
                        reply="Sorry, I can't answer right now.",
                        model=model_id,
                        total_ms=round((time.perf_counter() - started) * 1000),
                        tools=failed.calls + again.calls,
                        error=f"{failed.cause!r}; fallback: {again.cause!r}",
                    )
            self._sessions[session_id] = messages
            return Turn(
                reply=spoken(reply),
                model=model_id,
                total_ms=round((time.perf_counter() - started) * 1000),
                tools=recorder.calls,
            )

    def read_resource(self, uri: str) -> dict[str, Any]:
        """resources/read on the live server; returns the first text content item."""
        result = self.mcp.read_resource_sync(uri)
        for item in result.contents:
            text = getattr(item, "text", None)
            if text is not None:
                return {
                    "uri": str(item.uri),
                    "mimeType": item.mime_type,
                    "text": text,
                    "_meta": item.meta or {},
                }
        raise LookupError(f"no text content for {uri}")


class TurnFailed(Exception):
    def __init__(self, cause: BaseException, recorder: TurnRecorder) -> None:
        super().__init__(repr(cause))
        self.cause = cause
        self.calls = recorder.calls
