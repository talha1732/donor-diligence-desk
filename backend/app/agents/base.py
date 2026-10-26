"""Shared pieces for the four agents (owner: agents builder)."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import UsageLimits

from app.config import PROMPTS_DIR
from app.events import RunSession, truncate
from app.schemas import FinancialMetrics, OrgProfile


@dataclass(frozen=True)
class AgentLimits:
    requests: int
    tool_calls: int

    def usage_limits(self) -> UsageLimits:
        return UsageLimits(request_limit=self.requests, tool_calls_limit=self.tool_calls)


# Contract section 7: requests / tool calls per agent.
FINANCIAL_LIMITS = AgentLimits(requests=6, tool_calls=8)
IMPACT_LIMITS = AgentLimits(requests=8, tool_calls=6)
AUDITOR_LIMITS = AgentLimits(requests=4, tool_calls=6)
MEMO_LIMITS = AgentLimits(requests=3, tool_calls=0)

AGENT_RETRIES = 2
MODEL_SETTINGS: dict[str, Any] = {"max_tokens": 6000}


@dataclass
class AgentDeps:
    session: RunSession
    agent_key: str
    ein: str | None
    limits: AgentLimits
    profile: OrgProfile | None = None
    metrics: FinancialMetrics | None = None
    website_url: str | None = None
    tool_counts: dict[str, int] = field(default_factory=dict)
    pages_read: list[str] = field(default_factory=list)
    web_evidence_ids: list[str] = field(default_factory=list)

    def count(self, tool: str) -> int:
        self.tool_counts[tool] = self.tool_counts.get(tool, 0) + 1
        return self.tool_counts[tool]

    def tool_event(self, tool: str, args: dict, summary: str, started: float) -> None:
        self.session.tool_event(
            self.agent_key, self.ein, tool, args, summary, (time.perf_counter() - started) * 1000
        )


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Shared rules first, then the role prompt: identical across calls so prompt caching applies."""
    common = (PROMPTS_DIR / "common.md").read_text(encoding="utf-8").strip()
    role = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
    return f"{common}\n\n{role}\n"


async def hide_tools_when_spent(ctx: RunContext[AgentDeps], tool_def: ToolDefinition) -> ToolDefinition | None:
    """Withhold function tools for the last two allowed requests (or once the tool budget is used) so
    the model has to return its structured answer, with room for one output retry, instead of hitting
    a usage limit. run_step is the 1-based number of the request being prepared."""
    limits = ctx.deps.limits
    if ctx.run_step >= limits.requests - 1 or ctx.usage.tool_calls >= limits.tool_calls:
        return None
    return tool_def


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ": "))


_ID_CLEAN = re.compile(r"^[\s\[\(\"'`]+|[\s\]\)\"'`.,;]+$")


def clean_evidence_ids(ids: list[str]) -> list[str]:
    out: list[str] = []
    for raw in ids or []:
        ev_id = _ID_CLEAN.sub("", str(raw))
        if ev_id and ev_id not in out:
            out.append(ev_id)
    return out


def describe_org(profile: OrgProfile) -> str:
    lines = [f"Charity: {profile.name} (EIN {profile.ein})"]
    if profile.is_demo:
        lines.append("This is a fictional DEMO charity used to demonstrate the tool. Treat its data normally.")
    place = ", ".join(p for p in (profile.city, profile.state) if p)
    if place:
        lines.append(f"Location: {place}")
    if profile.ntee_code:
        lines.append(f"IRS activity code (NTEE): {profile.ntee_code}")
    if profile.subsection_code is not None:
        lines.append(f"IRS subsection: 501(c)({profile.subsection_code})")
    if profile.ruling_date:
        lines.append(f"IRS ruling date: {profile.ruling_date}")
    return "\n".join(lines)


def short(text: str | None, limit: int = 200) -> str:
    return truncate(re.sub(r"\s+", " ", text or ""), limit)
