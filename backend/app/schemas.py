"""Shared data models for Donor Diligence Desk.

FROZEN CONTRACT: every module imports these. Do not redefine them elsewhere.
Change requests go to the orchestrator (see AGENTS.md section 4).

Unit conventions for numeric values:
- usd: plain dollars (float), never thousands or millions
- ratio: a fraction (0.124 means 12.4%)
- months, years, count: plain numbers
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Unit = Literal["usd", "ratio", "months", "years", "count", "text"]

Dimension = Literal[
    "financial_health",
    "revenue_resilience",
    "cost_discipline",
    "transparency",
    "impact_evidence",
]
DIMENSIONS: list[str] = [
    "financial_health",
    "revenue_resilience",
    "cost_discipline",
    "transparency",
    "impact_evidence",
]
DIMENSION_LABELS: dict[str, str] = {
    "financial_health": "Financial health",
    "revenue_resilience": "Revenue resilience",
    "cost_discipline": "Cost discipline",
    "transparency": "Transparency",
    "impact_evidence": "Impact evidence",
}

Band = Literal["strong_fit", "fit_with_questions", "weak_fit", "insufficient_data"]


# --------------------------------------------------------------------------- request


class Weights(BaseModel):
    """Donor priority weights, 0 to 5 each. All zero is treated as equal weights."""

    financial_health: float = Field(1.0, ge=0, le=5)
    revenue_resilience: float = Field(1.0, ge=0, le=5)
    cost_discipline: float = Field(1.0, ge=0, le=5)
    transparency: float = Field(1.0, ge=0, le=5)
    impact_evidence: float = Field(1.0, ge=0, le=5)


class CharityInput(BaseModel):
    ein: str = Field(pattern=r"^\d{9}$", description="9-digit EIN, no dash")
    website_url: str | None = Field(None, max_length=500)

    @field_validator("website_url")
    @classmethod
    def _http_only(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError("website_url must start with http:// or https://")
        return v


class DiligenceRequest(BaseModel):
    charities: list[CharityInput] = Field(min_length=1, max_length=3)
    weights: Weights = Field(default_factory=Weights)
    donor_note: str = Field("", max_length=500)
    budget_usd: float | None = Field(None, gt=0, le=0.50)
    defenses_off: bool = Field(
        False, description="Honoured only when the server sets ALLOW_DEFENSE_TOGGLE=1 (safety demo)."
    )


# --------------------------------------------------------------------------- ProPublica data


class OrgSearchResult(BaseModel):
    ein: str
    name: str
    city: str | None = None
    state: str | None = None
    ntee_code: str | None = None
    subsection_code: int | None = None  # 3 means 501(c)(3)
    latest_revenue: float | None = None
    is_demo: bool = False


class FilingYear(BaseModel):
    tax_year: int
    tax_period: int | None = None  # YYYYMM
    form_type: str | None = None  # "990", "990EZ", "990PF"
    pdf_url: str | None = None
    total_revenue: float | None = None
    total_expenses: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    net_assets: float | None = None
    contributions: float | None = None
    program_service_revenue: float | None = None
    investment_income: float | None = None
    officer_compensation: float | None = None
    other_salaries: float | None = None
    payroll_tax: float | None = None
    professional_fundraising_fees: float | None = None
    fundraising_event_gross: float | None = None
    fundraising_event_direct_expenses: float | None = None


class OrgProfile(BaseModel):
    ein: str
    name: str
    city: str | None = None
    state: str | None = None
    ntee_code: str | None = None
    subsection_code: int | None = None
    ruling_date: str | None = None
    is_demo: bool = False
    website_url: str | None = None
    source_url: str  # ProPublica API URL (or "fixture:<file>" for demo data)
    filings: list[FilingYear] = Field(default_factory=list)  # newest first, filings with data only
    filings_without_data_years: list[int] = Field(default_factory=list)
    fetched_at: str  # ISO 8601
    from_cache: bool = False


# --------------------------------------------------------------------------- evidence ledger


class Evidence(BaseModel):
    """One traceable fact. Every number shown to a user must point to one of these.

    ID formats:
      PP-<ein>-<tax_year>-<field>     IRS field from ProPublica (field = FilingYear attribute)
      CALC-<ein>-<metric_key>         deterministic calculation (inputs lists the PP ids used)
      WEB-<ein>-<n>                   sanitized excerpt from a web page or search snippet
      USER-<n>                        something the donor typed
    """

    id: str
    kind: Literal["irs_field", "calculation", "web_excerpt", "user_input"]
    ein: str | None = None
    label: str
    value: float | None = None
    unit: Unit = "text"
    display: str
    source_url: str | None = None
    excerpt: str | None = None  # quote for web evidence, formula for calculations
    inputs: list[str] = Field(default_factory=list)
    tax_year: int | None = None


class Metric(BaseModel):
    key: str
    label: str
    value: float | None = None
    unit: Unit = "ratio"
    display: str | None = None
    evidence_id: str | None = None
    reason_missing: str | None = None
    tax_year: int | None = None


class FinancialMetrics(BaseModel):
    ein: str
    latest_tax_year: int | None = None
    years_of_data: int = 0
    metrics: dict[str, Metric] = Field(default_factory=dict)


# --------------------------------------------------------------------------- web


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""


class FetchedPage(BaseModel):
    url: str
    final_url: str | None = None
    status: int | None = None
    content_type: str | None = None
    html: str = ""
    error: str | None = None


class HiddenSegment(BaseModel):
    reason: str  # e.g. "display:none", "white-on-white", "html-comment", "aria-hidden", "font-size:0", "offscreen"
    text: str


class InjectionFinding(BaseModel):
    pattern: str
    snippet: str
    location: Literal["visible", "hidden", "user_input", "search_snippet"]


class SanitizedPage(BaseModel):
    url: str
    final_url: str | None = None
    title: str | None = None
    visible_text: str = ""
    hidden_segments: list[HiddenSegment] = Field(default_factory=list)
    injection_findings: list[InjectionFinding] = Field(default_factory=list)
    truncated: bool = False
    fetched_ok: bool = True
    error: str | None = None


# --------------------------------------------------------------------------- agent outputs


class FindingDraft(BaseModel):
    """What an LLM agent returns for one claim. The orchestrator assigns ids."""

    dimension: Dimension | Literal["mission_fit", "other"] = "other"
    stance: Literal["strength", "concern", "neutral"] = "neutral"
    text: str = Field(max_length=400)
    evidence_ids: list[str] = Field(default_factory=list)


class Finding(FindingDraft):
    id: str  # "F-<agent-key>-<n>"
    ein: str | None = None
    agent: str


class FinancialAgentOutput(BaseModel):
    summary: str = Field(max_length=600)
    findings: list[FindingDraft] = Field(default_factory=list, max_length=8)
    questions_for_charity: list[str] = Field(default_factory=list, max_length=5)
    could_not_verify: list[str] = Field(default_factory=list, max_length=5)


class ImpactAgentOutput(BaseModel):
    summary: str = Field(max_length=600)
    website_url: str | None = None
    evidence_level: int = Field(0, ge=0, le=4)
    evidence_level_rationale: str = Field("", max_length=400)
    publishes_financials: bool | None = None
    publishes_outcomes: bool | None = None
    mission_fit_note: str = Field("", max_length=300)
    findings: list[FindingDraft] = Field(default_factory=list, max_length=8)
    questions_for_charity: list[str] = Field(default_factory=list, max_length=5)
    could_not_verify: list[str] = Field(default_factory=list, max_length=5)


IMPACT_EVIDENCE_LEVELS: dict[int, str] = {
    0: "No information found about results",
    1: "Stories or anecdotes only",
    2: "Reports outputs (people served, meals, etc.)",
    3: "Reports measured outcomes against goals",
    4: "Independent evaluation or rigorous study",
}


class ImpactAssessment(BaseModel):
    ein: str
    website_url: str | None = None
    pages_read: list[str] = Field(default_factory=list)
    evidence_level: int = Field(0, ge=0, le=4)
    evidence_level_label: str = ""
    rationale: str = ""
    publishes_financials: bool | None = None
    publishes_outcomes: bool | None = None
    mission_fit_note: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class SpecialistReport(BaseModel):
    agent: str  # agent key, e.g. "financial:530196605"
    role: Literal["financial", "impact"]
    ein: str
    status: Literal["done", "error", "stopped"] = "done"
    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)
    questions_for_charity: list[str] = Field(default_factory=list)
    could_not_verify: list[str] = Field(default_factory=list)
    impact: ImpactAssessment | None = None
    error: str | None = None


# --------------------------------------------------------------------------- audit


class ClaimCheck(BaseModel):
    finding_id: str
    status: Literal["verified", "unverified_number", "missing_evidence", "unknown_evidence_id", "no_numbers"]
    numbers_checked: list[str] = Field(default_factory=list)
    unmatched_numbers: list[str] = Field(default_factory=list)
    detail: str = ""


class VerificationReport(BaseModel):
    checks: list[ClaimCheck] = Field(default_factory=list)
    verified_count: int = 0
    flagged_count: int = 0


class AuditorAgentOutput(BaseModel):
    notes: list[str] = Field(default_factory=list, max_length=8)
    remove_finding_ids: list[str] = Field(default_factory=list)
    extra_questions: dict[str, list[str]] = Field(default_factory=dict)  # ein -> questions


class AuditReport(BaseModel):
    verification: VerificationReport = Field(default_factory=VerificationReport)
    auditor_notes: list[str] = Field(default_factory=list)
    removed_finding_ids: list[str] = Field(default_factory=list)
    added_questions: dict[str, list[str]] = Field(default_factory=dict)


# --------------------------------------------------------------------------- scoring


class DimensionScore(BaseModel):
    dimension: Dimension
    label: str
    score: float | None = None  # 0-100, None when inputs are missing
    weight: float = 1.0
    drivers: list[str] = Field(default_factory=list)  # evidence ids
    explanation: str = ""
    missing_inputs: list[str] = Field(default_factory=list)


class CharityScorecard(BaseModel):
    ein: str
    name: str
    is_demo: bool = False
    dimensions: list[DimensionScore] = Field(default_factory=list)
    overall: float | None = None
    band: Band = "insufficient_data"


# --------------------------------------------------------------------------- memo


class MemoCharityDraft(BaseModel):
    ein: str
    one_line: str = Field(max_length=300)
    strength_finding_ids: list[str] = Field(default_factory=list, max_length=4)
    concern_finding_ids: list[str] = Field(default_factory=list, max_length=4)
    questions_for_charity: list[str] = Field(default_factory=list, max_length=5)


class MemoAgentOutput(BaseModel):
    headline: str = Field(max_length=200, description="Action title: one sentence stating the conclusion.")
    summary: str = Field(max_length=800)
    recommendation: str = Field(max_length=600)
    charities: list[MemoCharityDraft] = Field(default_factory=list)


class CharitySection(BaseModel):
    ein: str
    name: str
    is_demo: bool = False
    band: Band = "insufficient_data"
    overall: float | None = None
    one_line: str = ""
    strengths: list[Finding] = Field(default_factory=list)
    concerns: list[Finding] = Field(default_factory=list)
    questions_for_charity: list[str] = Field(default_factory=list)
    could_not_verify: list[str] = Field(default_factory=list)


class GivingMemo(BaseModel):
    headline: str
    summary: str
    recommendation: str
    charities: list[CharitySection] = Field(default_factory=list)
    method_note: str = ""
    disclaimer: str = "This memo is decision support, not financial, legal, or tax advice."
    text_checks: list[ClaimCheck] = Field(default_factory=list)  # verify_text results for headline/summary/etc.


# --------------------------------------------------------------------------- usage, safety, result


class AgentUsage(BaseModel):
    agent: str
    requests: int = 0
    input_tokens: int = 0  # inclusive of cached and cache-write tokens
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0


class RunUsage(BaseModel):
    model: str
    agents: list[AgentUsage] = Field(default_factory=list)
    total: AgentUsage = Field(default_factory=lambda: AgentUsage(agent="total"))
    budget_usd: float
    stopped_by_budget: bool = False


class SecurityEvent(BaseModel):
    kind: Literal[
        "hidden_text_removed",
        "injection_detected",
        "input_blocked",
        "url_blocked",
        "budget_stop",
        "daily_budget_stop",
        "rate_limited",
        "tool_limit",
        "unverified_claim",
    ]
    severity: Literal["info", "warning", "blocked"] = "warning"
    agent: str | None = None
    ein: str | None = None
    detail: str
    snippet: str | None = None


class DiligenceResult(BaseModel):
    run_id: str
    created_at: str
    status: Literal["complete", "stopped_budget", "error"] = "complete"
    error: str | None = None
    defenses_on: bool = True
    request: DiligenceRequest
    orgs: list[OrgSearchResult] = Field(default_factory=list)
    metrics: list[FinancialMetrics] = Field(default_factory=list)
    reports: list[SpecialistReport] = Field(default_factory=list)
    audit: AuditReport | None = None
    scorecards: list[CharityScorecard] = Field(default_factory=list)
    memo: GivingMemo | None = None
    evidence: dict[str, Evidence] = Field(default_factory=dict)
    security_events: list[SecurityEvent] = Field(default_factory=list)
    usage: RunUsage
