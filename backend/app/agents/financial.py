"""Financial Analyst agent: interprets deterministic Form 990 metrics (owner: agents builder)."""

from __future__ import annotations

import time

from pydantic_ai import Agent, RunContext

from app.agents.base import (
    AGENT_RETRIES,
    MODEL_SETTINGS,
    AgentDeps,
    compact_json,
    describe_org,
    hide_tools_when_spent,
    load_prompt,
)
from app.schemas import Evidence, FilingYear, FinancialAgentOutput, OrgProfile
from app.tools import financials

ROLE = "Financial Analyst"
FIELDS: tuple[str, ...] = tuple(
    name for name in FilingYear.model_fields if name not in {"tax_year", "tax_period", "form_type", "pdf_url"}
)

agent: Agent[AgentDeps, FinancialAgentOutput] = Agent(
    None,
    output_type=FinancialAgentOutput,
    deps_type=AgentDeps,
    instructions=load_prompt("financial"),
    name="financial",
    retries=AGENT_RETRIES,
    model_settings=MODEL_SETTINGS,
    defer_model_check=True,
)


def format_value(value: float | None, unit: str) -> str:
    fn = getattr(financials, "format_value", None)
    if fn is not None:
        try:
            return fn(value, unit)
        except Exception:
            pass
    if value is None:
        return "n/a"
    if unit == "ratio":
        return f"{value * 100:.1f}%"
    if unit == "usd":
        return f"${value:,.0f}"
    if unit == "months":
        return f"{value:.1f} months"
    return f"{value:g}"


def _compare_years_fallback(profile: OrgProfile, field: str, year_a: int, year_b: int) -> Evidence | None:
    """Same contract as financials.compare_years (section 12.3), used only if that helper is missing."""
    by_year = {f.tax_year: f for f in profile.filings}
    fa, fb = by_year.get(year_a), by_year.get(year_b)
    va = getattr(fa, field, None) if fa else None
    vb = getattr(fb, field, None) if fb else None
    if va is None or vb is None or va <= 0:
        return None
    change = (vb - va) / va
    sign = "+" if change >= 0 else ""
    return Evidence(
        id=f"CALC-{profile.ein}-{field}-chg-{year_a}-{year_b}",
        kind="calculation",
        ein=profile.ein,
        label=f"Change in {field.replace('_', ' ')} from {year_a} to {year_b}",
        value=change,
        unit="ratio",
        display=f"{sign}{change * 100:.1f}% ({year_a} to {year_b})",
        source_url=profile.source_url,
        excerpt=f"({field} {year_b} - {field} {year_a}) / {field} {year_a}",
        inputs=[f"PP-{profile.ein}-{year_a}-{field}", f"PP-{profile.ein}-{year_b}-{field}"],
        tax_year=year_b,
    )


@agent.tool(prepare=hide_tools_when_spent)
async def get_field_history(ctx: RunContext[AgentDeps], field: str) -> str:
    """Values of one Form 990 field for up to five recent tax years, newest first, with evidence ids.

    Args:
        field: A FilingYear field such as total_revenue, total_expenses, net_assets or contributions.
    """
    started = time.perf_counter()
    deps = ctx.deps
    field = (field or "").strip()
    if field not in FIELDS:
        result = f"Unknown field {field!r}. Valid fields: {', '.join(FIELDS)}."
        deps.tool_event("get_field_history", {"field": field}, "unknown field", started)
        return result
    try:
        rows = financials.field_history(deps.profile, field, years=5)
    except Exception as exc:
        deps.tool_event("get_field_history", {"field": field}, f"error: {exc}", started)
        return f"Could not read the history of {field}: {type(exc).__name__}."
    values = []
    for row in rows:
        ev_id = row.get("evidence_id")
        display = row.get("display") or (format_value(row.get("value"), "usd") if row.get("value") is not None else None)
        if ev_id and display:
            values.append({"tax_year": row.get("tax_year"), "display": display, "evidence_id": ev_id})
        else:
            values.append({"tax_year": row.get("tax_year"), "display": "not reported", "evidence_id": None})
    summary = f"{len([v for v in values if v['evidence_id']])} years with data"
    deps.tool_event("get_field_history", {"field": field}, summary, started)
    if not values:
        return f"No values of {field} are available for this charity."
    return compact_json({"field": field, "values": values})


@agent.tool(prepare=hide_tools_when_spent)
async def get_metric(ctx: RunContext[AgentDeps], key: str) -> str:
    """One deterministic metric with its display value, formula, inputs and CALC evidence id.

    Args:
        key: A metric key from the table in the task prompt, for example surplus_margin.
    """
    started = time.perf_counter()
    deps = ctx.deps
    key = (key or "").strip()
    metrics = deps.metrics.metrics if deps.metrics else {}
    metric = metrics.get(key)
    if metric is None:
        deps.tool_event("get_metric", {"key": key}, "unknown metric", started)
        return f"Unknown metric {key!r}. Valid keys: {', '.join(metrics)}."
    data = {
        "key": metric.key,
        "label": metric.label,
        "display": metric.display if metric.value is not None else None,
        "evidence_id": metric.evidence_id,
        "tax_year": metric.tax_year,
        "reason_missing": metric.reason_missing,
    }
    ev = deps.session.evidence.get(metric.evidence_id or "")
    if ev is not None:
        data["formula"] = ev.excerpt
        data["inputs"] = ev.inputs
    summary = metric.display if metric.value is not None else f"missing: {metric.reason_missing or 'n/a'}"
    deps.tool_event("get_metric", {"key": key}, summary or "", started)
    return compact_json(data)


@agent.tool(prepare=hide_tools_when_spent)
async def compare_years(ctx: RunContext[AgentDeps], field: str, year_a: int, year_b: int) -> str:
    """Deterministic percent change of one Form 990 field from tax year year_a to tax year year_b.
    Registers a new CALC evidence id for the change that you can cite.

    Args:
        field: A FilingYear field such as total_revenue or total_expenses.
        year_a: The earlier tax year (the base).
        year_b: The later tax year.
    """
    started = time.perf_counter()
    deps = ctx.deps
    args = {"field": field, "year_a": year_a, "year_b": year_b}
    field = (field or "").strip()
    if field not in FIELDS:
        deps.tool_event("compare_years", args, "unknown field", started)
        return f"Unknown field {field!r}. Valid fields: {', '.join(FIELDS)}."
    fn = getattr(financials, "compare_years", None) or _compare_years_fallback
    try:
        ev = fn(deps.profile, field, int(year_a), int(year_b))
    except Exception as exc:
        deps.tool_event("compare_years", args, f"error: {type(exc).__name__}", started)
        return f"Could not compare {field} between {year_a} and {year_b}."
    if ev is None:
        deps.tool_event("compare_years", args, "not computable", started)
        return (
            f"Cannot compute the change in {field} from {year_a} to {year_b}: a value is missing or the base "
            "year value is zero or negative. Describe the trend in words or ask the charity."
        )
    deps.session.add_evidence([ev])
    deps.tool_event("compare_years", args, f"{ev.id} = {ev.display}", started)
    return compact_json({"evidence_id": ev.id, "label": ev.label, "display": ev.display})


def build_prompt(profile: OrgProfile, metrics, evidence: dict[str, Evidence]) -> str:
    lines = [describe_org(profile), ""]
    if profile.filings:
        years = ", ".join(f"{f.tax_year} (Form {f.form_type or '990'})" for f in profile.filings)
        lines.append(f"Tax years with financial data, newest first: {years}")
    else:
        lines.append("No tax years with financial data are available.")
    if profile.filings_without_data_years:
        lines.append(
            "Tax years filed but without data in the free extract: "
            + ", ".join(str(y) for y in profile.filings_without_data_years)
        )
    lines.append("")
    lines.append("Deterministic metrics (display value and the evidence id to cite):")
    for key, m in (metrics.metrics if metrics else {}).items():
        if m.value is not None and m.evidence_id:
            year = f", tax year {m.tax_year}" if m.tax_year else ""
            lines.append(f"- {key} ({m.label}{year}): {m.display or format_value(m.value, m.unit)} [{m.evidence_id}]")
        else:
            lines.append(f"- {key} ({m.label}): not available. Reason: {m.reason_missing or 'not computable'}")
    lines.append("")
    lines.append(
        "Use your tools to look at multi-year trends, then return your FinancialAgentOutput. "
        "Quote only display values given above or returned by tools, with their evidence ids."
    )
    return "\n".join(lines)


def summarize(output: FinancialAgentOutput) -> str:
    return output.summary
