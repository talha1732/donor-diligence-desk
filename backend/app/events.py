"""Event bus and traced agent runner (owner: agents builder).

RunSession holds everything one diligence run shares: the ordered event log (section 12.4), an
asyncio.Queue for the SSE stream, the evidence ledger, security events and the BudgetTracker.
run_agent() runs a PydanticAI agent node by node so every model request and response becomes an
agent_step event and every response's usage is recorded against the budget as soon as it arrives.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel

from app.cost import pricing
from app.cost.budget import BudgetExceeded, BudgetTracker
from app.schemas import Evidence, SecurityEvent

STEP_TEXT_LIMIT = 600
ARGS_TEXT_LIMIT = 300
OUTPUT_TOOL_PREFIX = "final_result"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def truncate(text: str | None, limit: int = STEP_TEXT_LIMIT) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class RunSession:
    """Per-run shared state and event emitter."""

    def __init__(
        self,
        run_id: str,
        *,
        model_name: str,
        budget: BudgetTracker,
        defenses_on: bool = True,
        deadline: float | None = None,
        queue: asyncio.Queue | None = None,
    ) -> None:
        self.run_id = run_id
        self.model_name = model_name
        self.budget = budget
        self.defenses_on = defenses_on
        self.deadline = deadline if deadline is not None else time.monotonic() + 240.0
        self.queue = queue
        self.events: list[dict] = []
        self.evidence: dict[str, Evidence] = {}
        self.security_events: list[SecurityEvent] = []
        self.stopped_by_budget = False
        self._web_counters: dict[str, int] = {}
        self._finding_counters: dict[str, int] = {}

    # ------------------------------------------------------------------ events

    def emit(self, type_: str, data: Any, *, queue: bool = True) -> dict:
        event = {"type": type_, "ts": now_iso(), "data": _jsonable(data)}
        self.events.append(event)
        if queue and self.queue is not None:
            self.queue.put_nowait(event)
        return event

    def stage(self, stage: str, status: str) -> None:
        self.emit("stage", {"stage": stage, "status": status})

    def security(self, event: SecurityEvent) -> None:
        self.security_events.append(event)
        self.emit("security", event)

    def emit_spend(self) -> None:
        self.emit("spend", self.budget.snapshot(stopped_by_budget=self.stopped_by_budget))

    def tool_event(self, agent: str, ein: str | None, tool: str, args: dict, result_summary: str, ms: float) -> None:
        self.emit(
            "tool_call",
            {
                "agent": agent,
                "ein": ein,
                "tool": tool,
                "args": {k: truncate(str(v), ARGS_TEXT_LIMIT) for k, v in args.items()},
                "result_summary": truncate(result_summary, 300),
                "ms": round(ms, 1),
            },
        )

    # ------------------------------------------------------------------ ledger

    def add_evidence(self, entries: dict[str, Evidence] | list[Evidence]) -> list[str]:
        items = list(entries.values()) if isinstance(entries, dict) else list(entries)
        new_ids = []
        for ev in items:
            if ev.id not in self.evidence:
                new_ids.append(ev.id)
            self.evidence[ev.id] = ev
        if new_ids:
            self.emit("evidence_added", {"ids": new_ids, "count": len(new_ids), "total": len(self.evidence)})
        return new_ids

    def next_web_id(self, ein: str) -> str:
        n = self._web_counters.get(ein, 0) + 1
        self._web_counters[ein] = n
        return f"WEB-{ein}-{n}"

    def next_finding_id(self, agent_key: str) -> str:
        n = self._finding_counters.get(agent_key, 0) + 1
        self._finding_counters[agent_key] = n
        return f"F-{agent_key}-{n}"

    def remaining_seconds(self) -> float:
        return self.deadline - time.monotonic()


# ---------------------------------------------------------------------- traced runner


@dataclass
class AgentOutcome:
    agent: str
    status: str  # "done" | "error" | "stopped"
    output: Any = None
    error: str | None = None
    seconds: float = 0.0
    extra: dict = field(default_factory=dict)


def _usage_fields(usage: Any) -> dict[str, int]:
    def g(name: str) -> int:
        try:
            return int(getattr(usage, name, 0) or 0)
        except (TypeError, ValueError):
            return 0

    return {
        "input_tokens": g("input_tokens"),
        "cached_tokens": g("cache_read_tokens"),
        "cache_write_tokens": g("cache_write_tokens"),
        "output_tokens": g("output_tokens"),
    }


def _describe_request(request: Any) -> str:
    parts = getattr(request, "parts", []) or []
    bits: list[str] = []
    tool_returns = [getattr(p, "tool_name", "?") for p in parts if type(p).__name__ == "ToolReturnPart"]
    if tool_returns:
        real = [t for t in tool_returns if not str(t).startswith(OUTPUT_TOOL_PREFIX)]
        if real:
            bits.append("Tool results sent back: " + ", ".join(real))
    for p in parts:
        kind = type(p).__name__
        if kind == "UserPromptPart":
            content = p.content if isinstance(p.content, str) else str(p.content)
            bits.append(f"Task prompt sent ({len(content)} characters of charity data and instructions)")
        elif kind == "RetryPromptPart":
            bits.append("Asked the model to fix its last reply: " + truncate(str(getattr(p, "content", "")), 200))
    return truncate(" | ".join(bits) or "Model request")


def _describe_response(response: Any) -> tuple[str, list[dict], int, bool]:
    texts: list[str] = []
    calls: list[dict] = []
    function_calls = 0
    final = False
    for p in getattr(response, "parts", []) or []:
        kind = type(p).__name__
        if kind == "TextPart":
            texts.append(p.content)
        elif kind == "ToolCallPart":
            if str(p.tool_name).startswith(OUTPUT_TOOL_PREFIX):
                final = True
                continue
            function_calls += 1
            try:
                args = p.args_as_dict()
            except Exception:
                args = {"raw": str(p.args)}
            calls.append({"tool": p.tool_name, "args": {k: truncate(str(v), ARGS_TEXT_LIMIT) for k, v in args.items()}})
    text = " ".join(t for t in texts if t).strip()
    if final and not text:
        text = "Structured answer returned."
    elif calls and not text:
        text = "Calling " + ", ".join(c["tool"] for c in calls) + "."
    return truncate(text), calls, function_calls, final


async def run_agent(
    session: RunSession,
    *,
    agent: Any,
    agent_key: str,
    role: str,
    label: str,
    ein: str | None,
    prompt: str,
    deps: Any,
    usage_limits: Any,
    timeout: float,
    model: Any = None,
    summarize: Callable[[Any], str] | None = None,
) -> AgentOutcome:
    """Run one agent with limits and a timeout, emitting agent_started / agent_step / spend / agent_done.

    Agent errors (model errors, timeouts, usage limits, bad output) are returned as status "error".
    BudgetExceeded and cancellation are re-raised after agent_done(status="stopped") so the
    orchestrator can stop the whole run.
    """
    session.emit("agent_started", {"agent": agent_key, "role": role, "ein": ein, "label": label})
    started = time.monotonic()
    last_mark = started
    step = 0
    timeout = max(1.0, min(timeout, session.remaining_seconds()))

    def done(status: str, summary: str, error: str | None = None, output: Any = None) -> AgentOutcome:
        seconds = time.monotonic() - started
        usage = session.budget.agent_usage(agent_key)
        usage_dump = usage.model_dump(mode="json")
        usage_dump["seconds"] = round(seconds, 2)
        session.emit(
            "agent_done",
            {"agent": agent_key, "ein": ein, "status": status, "usage": usage_dump, "summary": truncate(summary, 600)},
        )
        return AgentOutcome(agent=agent_key, status=status, output=output, error=error, seconds=seconds)

    try:
        async with asyncio.timeout(timeout):
            async with agent.iter(prompt, deps=deps, usage_limits=usage_limits, model=model) as agent_run:
                async for node in agent_run:
                    kind = type(node).__name__
                    if kind == "ModelRequestNode":
                        step += 1
                        session.emit(
                            "agent_step",
                            {
                                "agent": agent_key,
                                "ein": ein,
                                "step": step,
                                "kind": "model_request",
                                "text": _describe_request(node.request),
                            },
                        )
                    elif kind == "CallToolsNode":
                        response = node.model_response
                        text, calls, n_calls, _final = _describe_response(response)
                        u = _usage_fields(response.usage)
                        now = time.monotonic()
                        seconds, last_mark = now - last_mark, now
                        cost = pricing.cost_usd(
                            session.model_name,
                            u["input_tokens"],
                            u["output_tokens"],
                            u["cached_tokens"],
                            u["cache_write_tokens"],
                        )
                        session.emit(
                            "agent_step",
                            {
                                "agent": agent_key,
                                "ein": ein,
                                "step": step,
                                "kind": "model_response",
                                "text": text,
                                "tool_calls": calls,
                                "usage": {**u, "cost_usd": cost, "seconds": round(seconds, 2)},
                            },
                        )
                        try:
                            session.budget.record(
                                agent_key,
                                input_tokens=u["input_tokens"],
                                output_tokens=u["output_tokens"],
                                cached_tokens=u["cached_tokens"],
                                cache_write_tokens=u["cache_write_tokens"],
                                requests=1,
                                tool_calls=n_calls,
                                seconds=seconds,
                            )
                        finally:
                            session.emit_spend()
                    elif kind == "End":
                        session.emit(
                            "agent_step",
                            {"agent": agent_key, "ein": ein, "step": step, "kind": "end", "text": "Finished."},
                        )
            output = agent_run.result.output if agent_run.result is not None else None
    except BudgetExceeded:
        done("stopped", "Stopped: the run reached its budget cap.")
        raise
    except asyncio.CancelledError:
        done("stopped", "Stopped before finishing.")
        raise
    except TimeoutError:
        msg = f"Timed out after {timeout:.0f} seconds."
        return done("error", msg, error=msg)
    except Exception as exc:  # any agent failure becomes an error report, never a crashed run
        msg = f"{type(exc).__name__}: {truncate(str(exc), 300)}"
        return done("error", "Agent error: " + msg, error=msg)

    if output is None:
        return done("error", "The agent returned no output.", error="no output")
    output = scrub_style(output)
    summary = ""
    if summarize is not None:
        try:
            summary = summarize(output)
        except Exception:
            summary = ""
    return done("done", summary or "Done.", output=output)


_EM_DASH = re.compile("\\s*\u2014\\s*")


def scrub_style(obj: Any) -> Any:
    """Replace em dashes in model-written text (house style) without re-validating the model."""
    if isinstance(obj, str):
        return _EM_DASH.sub(", ", obj)
    if isinstance(obj, list):
        return [scrub_style(v) for v in obj]
    if isinstance(obj, dict):
        return {k: scrub_style(v) for k, v in obj.items()}
    if isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            setattr(obj, name, scrub_style(getattr(obj, name)))
    return obj


def sse_format(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
