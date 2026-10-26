"""Red-Team Auditor agent: reviews findings, verification status and security events (owner: agents builder)."""

from __future__ import annotations

import time

from pydantic_ai import Agent, RunContext

from app.agents.base import (
    AGENT_RETRIES,
    MODEL_SETTINGS,
    AgentDeps,
    compact_json,
    hide_tools_when_spent,
    load_prompt,
    short,
)
from app.safety import sanitize
from app.schemas import AuditorAgentOutput, ClaimCheck, Finding, OrgProfile, SecurityEvent

ROLE = "Red-Team Auditor"
MAX_LOOKUPS = 5

agent: Agent[AgentDeps, AuditorAgentOutput] = Agent(
    None,
    output_type=AuditorAgentOutput,
    deps_type=AgentDeps,
    instructions=load_prompt("auditor"),
    name="auditor",
    retries=AGENT_RETRIES,
    model_settings=MODEL_SETTINGS,
    defer_model_check=True,
)


@agent.tool(prepare=hide_tools_when_spent)
async def get_evidence(ctx: RunContext[AgentDeps], evidence_id: str) -> str:
    """Return one evidence ledger entry: label, value, display string, source, quote or formula, inputs.

    Args:
        evidence_id: An id exactly as cited in a finding, for example PP-061063025-2023-total_revenue.
    """
    started = time.perf_counter()
    deps = ctx.deps
    evidence_id = (evidence_id or "").strip()
    args = {"evidence_id": evidence_id}
    if deps.count("get_evidence") > MAX_LOOKUPS:
        deps.tool_event("get_evidence", args, "refused: limit reached", started)
        return f"Limit reached: get_evidence may be called at most {MAX_LOOKUPS} times. Write your answer now."
    ev = deps.session.evidence.get(evidence_id)
    if ev is None:
        deps.tool_event("get_evidence", args, "unknown id", started)
        return f"{evidence_id!r} is not in the evidence ledger."
    data = {
        "id": ev.id,
        "kind": ev.kind,
        "ein": ev.ein,
        "label": ev.label,
        "display": ev.display,
        "unit": ev.unit,
        "tax_year": ev.tax_year,
        "source_url": ev.source_url,
        "inputs": ev.inputs,
    }
    excerpt = short(ev.excerpt, 400) if ev.excerpt else None
    deps.tool_event("get_evidence", args, f"{ev.kind}: {short(ev.display, 80)}", started)
    if ev.kind == "web_excerpt" and excerpt:
        quote = sanitize.wrap_untrusted(excerpt, ev.source_url or "web") if deps.session.defenses_on else excerpt
        return compact_json(data) + "\nQuote:\n" + quote
    data["formula_or_quote"] = excerpt
    return compact_json(data)


def build_prompt(
    profiles: list[OrgProfile],
    findings: list[Finding],
    checks: dict[str, ClaimCheck],
    security_events: list[SecurityEvent],
    questions: dict[str, list[str]],
    donor_note: str = "",
) -> str:
    names = {p.ein: p.name for p in profiles}
    note = donor_note.strip()
    lines = [
        f'Donor\'s note [USER-1] (mission findings may refer to it): "{note}"' if note else "Donor's note: none was given.",
        "",
        "Findings to review, grouped by charity:",
    ]
    for profile in profiles:
        lines.append("")
        lines.append(f"## {profile.name} (EIN {profile.ein})")
        own = [f for f in findings if f.ein == profile.ein]
        if not own:
            lines.append("(no findings)")
        for f in own:
            check = checks.get(f.id)
            status = check.status if check else "not checked"
            unmatched = f"; unmatched numbers: {', '.join(check.unmatched_numbers)}" if check and check.unmatched_numbers else ""
            lines.append(
                f"- {f.id} [{f.agent}, {f.stance}, {f.dimension}] {f.text} "
                f"(evidence: {', '.join(f.evidence_ids) or 'none'}; verification: {status}{unmatched})"
            )
        qs = questions.get(profile.ein) or []
        if qs:
            lines.append("Questions proposed by the specialists:")
            lines.extend(f"- {q}" for q in qs)
    lines.append("")
    lines.append("Security events recorded in this run:")
    if not security_events:
        lines.append("- none")
    for ev in security_events:
        who = names.get(ev.ein or "", ev.ein or "run")
        lines.append(f"- {ev.kind} ({ev.severity}) for {who}: {ev.detail}")
    lines.append("")
    lines.append("Review the findings and return your AuditorAgentOutput.")
    return "\n".join(lines)


def summarize(output: AuditorAgentOutput) -> str:
    removed = len(output.remove_finding_ids)
    return f"{len(output.notes)} audit notes; recommended removing {removed} finding(s)."
