"""Triage agent: Strands Agents + Amazon Bedrock writes the incident's spoken summary.

Async only (triage Lambda). Contract:
- Input: only the incident's current signals (headline, description, instruction) and evidence.
- Output: JSON matching TriageOutput's schema (validated), spoken_summary ≤ 40 words.
- Grounding: every number, time word, and name must appear in the source text, else rejected.
  Replays run in strict mode: no days, dates, or clock times at all (their prose keeps the original
  days while timestamps are shifted); the shifted end time is appended by us, not the model.
- No URLs or domains in spoken text: an action containing one is dropped; a summary containing
  one keeps the template for that field.
- Models tried in order (Nova Lite, then Claude Haiku) inside one 8 s budget; then the template.
"""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from nightwatch_core.models import Evidence, Signal
from nightwatch_pipeline.triage import grounding

BUDGET_S = 8.0
MIN_ATTEMPT_S = 1.5
MAX_SPOKEN_WORDS = 40

SYSTEM_PROMPT = """You write alerts for a household voice assistant, read aloud to someone who \
just woke up. Be calm, plain, and short.

Rules:
- Use ONLY facts stated in the alert text you are given. Never add numbers, times, places, or \
causes that are not written there.
- Write times and days exactly as the alert states them. Do not say "today", "tonight", or \
"tomorrow" unless the alert text says it.
- spoken_summary: at most 40 words, one or two sentences, what is happening and until when.
- detail_summary: two to four sentences with the key details from the alert.
- recommended_actions: one to three short imperative actions taken from the alert's instructions \
or plainly implied by them.
- Never mention IDs, URLs, or codes.

Reply with ONLY a JSON object matching this JSON schema, no other text:
"""

REPLAY_RULES = """
REPLAY MODE: this is a replay of an archived alert. Do NOT state any days, dates, clock times, \
or words like today, tonight, tomorrow, this evening, or weekend, anywhere in your output. \
Describe only the hazard and what to do; the app adds the timing. Keep spoken_summary to at \
most 32 words.
"""


class TriageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spoken_summary: str = Field(min_length=1, max_length=400)
    detail_summary: str = Field(min_length=1, max_length=1500)
    recommended_actions: list[str] = Field(min_length=1, max_length=3)

    @field_validator("spoken_summary")
    @classmethod
    def _short(cls, v: str) -> str:
        if len(v.split()) > MAX_SPOKEN_WORDS:
            raise ValueError(f"spoken_summary over {MAX_SPOKEN_WORDS} words")
        return v

    @field_validator("recommended_actions")
    @classmethod
    def _actions(cls, v: list[str]) -> list[str]:
        if any(not a.strip() or len(a) > 160 for a in v):
            raise ValueError("actions must be short and non-empty")
        return v


OUTPUT_SCHEMA = json.dumps(TriageOutput.model_json_schema())


def source_text(signals: list[Signal], evidence: list[Evidence]) -> str:
    """Everything the model is allowed to say. Also the grounding reference."""
    parts: list[str] = []
    for s in signals:
        parts += [f"EVENT: {s.event}", f"HEADLINE: {s.headline}"]
        if s.description:
            parts.append(f"DESCRIPTION: {s.description}")
        if s.instruction:
            parts.append(f"INSTRUCTION: {s.instruction}")
    parts += [f"EVIDENCE: {e.detail}" for e in evidence]
    return "\n".join(parts)


def build_prompt(signals: list[Signal], evidence: list[Evidence]) -> str:
    return (
        "Alert text:\n<<<\n" + source_text(signals, evidence) + "\n>>>\nWrite the JSON object now."
    )


def parse_output(text: str) -> TriageOutput:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object in model output")
    return TriageOutput.model_validate_json(match.group(0))


Invoke = Callable[[str, str, str, float], str]  # (model_id, system, prompt, timeout_s) -> text


def invoke_bedrock(model_id: str, system: str, prompt: str, timeout_s: float) -> str:
    """One Strands agent turn, no tools. Imported lazily: Strands is only in the triage zip."""
    from botocore.config import Config
    from strands import Agent
    from strands.models.bedrock import BedrockModel

    model = BedrockModel(
        model_id=model_id,
        streaming=False,  # Converse (bedrock:InvokeModel), no response stream
        temperature=0.2,
        max_tokens=700,
        boto_client_config=Config(
            connect_timeout=2, read_timeout=timeout_s, retries={"max_attempts": 1}
        ),
    )
    agent = Agent(model=model, system_prompt=system, callback_handler=None)
    return str(agent(prompt))


@dataclass
class TriageResult:
    fields: dict[str, Any] | None  # accepted fields to write; None = keep the template
    model: str
    latency_ms: int
    grounding_passed: bool | None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    template_fields: list[str] = field(default_factory=list)  # kept from the template

    @property
    def fallback_used(self) -> bool:
        return self.fields is None


def without_urls(out: TriageOutput) -> tuple[dict[str, Any], list[str], int]:
    """(fields safe to speak, fields that keep the template, number of actions dropped)."""
    fields: dict[str, Any] = {}
    template: list[str] = []
    for name in ("spoken_summary", "detail_summary"):
        value = getattr(out, name)
        if grounding.has_url(value):
            template.append(name)
        else:
            fields[name] = value
    actions = [a for a in out.recommended_actions if not grounding.has_url(a)]
    if actions:
        fields["recommended_actions"] = actions
    else:
        template.append("recommended_actions")
    return fields, template, len(out.recommended_actions) - len(actions)


def summarize(
    signals: list[Signal],
    evidence: list[Evidence],
    models: list[str],
    invoke: Invoke = invoke_bedrock,
    budget_s: float = BUDGET_S,
    clock: Callable[[], float] = time.monotonic,
    *,
    replay: bool = False,
    spoken_suffix: str | None = None,
) -> TriageResult:
    """Try each model in order within the budget; first grounded output wins.

    `replay` turns on strict grounding (no timing words). `spoken_suffix` (the until-time we
    computed) is appended to the accepted spoken_summary; the total must stay ≤ 40 words.
    """
    source = source_text(signals, evidence)
    prompt = build_prompt(signals, evidence)
    system = SYSTEM_PROMPT + OUTPUT_SCHEMA + (REPLAY_RULES if replay else "")
    start = clock()
    attempts: list[dict[str, Any]] = []
    last_grounding: bool | None = None
    for model_id in models:
        remaining = budget_s - (clock() - start)
        if remaining < MIN_ATTEMPT_S:
            attempts.append({"model": model_id, "error": "budget exhausted"})
            break
        t0 = clock()
        try:
            out = parse_output(invoke(model_id, system, prompt, remaining))
        except (ValidationError, ValueError) as e:
            attempts.append({"model": model_id, "error": f"invalid output: {e}"[:300]})
            continue
        except Exception as e:  # Bedrock / network / timeout
            attempts.append({"model": model_id, "error": f"{type(e).__name__}: {e}"[:300]})
            continue
        ms = int((clock() - t0) * 1000)
        fields, template_fields, dropped = without_urls(out)
        texts = [
            *(fields[k] for k in ("spoken_summary", "detail_summary") if k in fields),
            *fields.get("recommended_actions", []),
        ]
        check = grounding.check(texts, source, strict=replay)
        last_grounding = check.passed
        attempt: dict[str, Any] = {
            "model": model_id, "latency_ms": ms, "grounded": check.passed,
            "violations": check.violations, "spoken_summary": out.spoken_summary,
            "url_fields": template_fields, "dropped_actions": dropped,
        }  # fmt: skip
        attempts.append(attempt)
        if not check.passed or not fields:
            continue
        if spoken_suffix and "spoken_summary" in fields:
            spoken = f"{fields['spoken_summary'].rstrip()} {spoken_suffix}"
            if len(spoken.split()) > MAX_SPOKEN_WORDS:
                attempt["error"] = f"over {MAX_SPOKEN_WORDS} words with the until-time"
                continue
            fields["spoken_summary"] = spoken
        return TriageResult(fields, model_id, ms, True, attempts, template_fields)
    total_ms = int((clock() - start) * 1000)
    last_model = attempts[-1]["model"] if attempts else "none"
    return TriageResult(None, last_model, total_ms, last_grounding, attempts)
