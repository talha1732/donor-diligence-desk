"""Deterministic 0-100 scoring rubric (owner: data and scoring builder).

The rubric is documented in docs/scoring-rubric.md and labelled as a hypothesis-based rubric in the UI.
Each input gets a piecewise-linear sub-score between the breakpoints in RUBRIC (flat beyond the ends);
a dimension is the mean of its available sub-scores; overall is the weighted mean of available dimensions.
"""

from __future__ import annotations

from app.schemas import (
    DIMENSION_LABELS,
    DIMENSIONS,
    IMPACT_EVIDENCE_LEVELS,
    CharityScorecard,
    DimensionScore,
    FinancialMetrics,
    ImpactAssessment,
    Metric,
    OrgProfile,
    Weights,
)
from app.tools.financials import format_value

# Breakpoints (input value, sub-score). Keep in sync with docs/scoring-rubric.md.
RUBRIC: dict[str, tuple[tuple[float, float], ...]] = {
    "surplus_margin": ((-0.10, 0.0), (0.0, 50.0), (0.05, 100.0)),
    "avg_surplus_margin_3y": ((-0.10, 0.0), (0.0, 50.0), (0.05, 100.0)),
    "net_assets_months": ((1.0, 0.0), (6.0, 100.0)),
    "liabilities_to_assets": ((0.30, 100.0), (0.70, 0.0)),
    "revenue_concentration_hhi": ((0.40, 100.0), (1.00, 50.0)),
    "revenue_volatility_cv": ((0.05, 100.0), (0.15, 70.0), (0.40, 0.0)),
    "revenue_cagr_3y": ((-0.10, 0.0), (0.0, 60.0), (0.05, 100.0)),
    "officer_comp_share": ((0.05, 100.0), (0.15, 60.0), (0.30, 0.0)),
    "pro_fundraising_fee_share": ((0.02, 100.0), (0.10, 50.0), (0.20, 0.0)),
    "expense_growth_gap": ((0.0, 100.0), (0.05, 50.0), (0.10, 0.0)),
    "filing_recency_years": ((3.0, 100.0), (5.0, 0.0)),
    "years_of_filings": ((0.0, 0.0), (1.0, 20.0), (3.0, 70.0), (5.0, 100.0)),
}
BAND_STRONG = 70.0
BAND_FIT = 50.0


def interpolate(x: float, points: tuple[tuple[float, float], ...]) -> float:
    """Piecewise-linear score, clamped to the first and last breakpoint."""
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _sentence(parts: list[str], missing_note: str = "") -> str:
    text = _join(parts)
    if missing_note:
        text = f"{text}; {missing_note}" if text else missing_note
    return text[:1].upper() + text[1:] + "." if text else ""


def _years(n: float) -> str:
    return f"{format_value(n, 'years')} year{'' if n == 1 else 's'}"


def _signed(m: Metric) -> str:
    return format_value(m.value, m.unit)


def _growth(m: Metric) -> str:
    """Signed so the number matches its evidence entry."""
    return f"grew {_signed(m)}" if m.value >= 0 else f"changed by {_signed(m)}"


class _Dim:
    """Collects sub-scores, drivers and missing inputs for one dimension."""

    def __init__(self, metrics: FinancialMetrics) -> None:
        self.metrics = metrics.metrics
        self.subscores: list[float] = []
        self.drivers: list[str] = []
        self.missing: list[str] = []

    def get(self, key: str) -> Metric | None:
        """The metric if it has a value; otherwise records it as missing and returns None."""
        m = self.metrics.get(key)
        if m is None or m.value is None:
            self.missing.append(key)
            return None
        if m.evidence_id:
            self.drivers.append(m.evidence_id)
        return m

    def result(self, dimension: str, weight: float, explanation: str, score: float | None = None) -> DimensionScore:
        if score is None:
            score = _mean(self.subscores)
        return DimensionScore(
            dimension=dimension,  # type: ignore[arg-type]
            label=DIMENSION_LABELS[dimension],
            score=None if score is None else round(score, 1),
            weight=weight,
            drivers=list(dict.fromkeys(self.drivers)),
            explanation=explanation,
            missing_inputs=list(dict.fromkeys(self.missing)),
        )


def _financial_health(metrics: FinancialMetrics, weight: float) -> DimensionScore:
    d = _Dim(metrics)
    margin, avg = d.get("surplus_margin"), d.get("avg_surplus_margin_3y")
    reserves, leverage = d.get("net_assets_months"), d.get("liabilities_to_assets")
    margin_scores = [interpolate(m.value, RUBRIC[m.key]) for m in (margin, avg) if m is not None]
    if margin_scores:
        d.subscores.append(sum(margin_scores) / len(margin_scores))
    for m in (reserves, leverage):
        if m is not None:
            d.subscores.append(interpolate(m.value, RUBRIC[m.key]))

    parts = []
    if reserves:
        parts.append(f"net assets cover {_signed(reserves)} of expenses")
    if leverage:
        parts.append(f"liabilities are {_signed(leverage)} of assets")
    if margin and avg:
        parts.append(f"the latest surplus margin is {_signed(margin)} (3-year average {_signed(avg)})")
    elif margin:
        parts.append(f"the latest surplus margin is {_signed(margin)}")
    elif avg:
        parts.append(f"the 3-year average surplus margin is {_signed(avg)}")
    gaps = []
    if not margin and not avg:
        gaps.append("the surplus margin")
    if not reserves:
        gaps.append("the reserves proxy")
    if not leverage:
        gaps.append("liabilities to assets")
    note = f"{_join(gaps)} could not be computed from the filings" if gaps else ""
    return d.result("financial_health", weight, _sentence(parts, note))


def _revenue_resilience(metrics: FinancialMetrics, weight: float) -> DimensionScore:
    d = _Dim(metrics)
    hhi, cv, cagr = d.get("revenue_concentration_hhi"), d.get("revenue_volatility_cv"), d.get("revenue_cagr_3y")
    for m in (hhi, cv, cagr):
        if m is not None:
            d.subscores.append(interpolate(m.value, RUBRIC[m.key]))

    parts = []
    if cagr:
        parts.append(f"revenue {_growth(cagr)} a year over about 3 years")
    if cv:
        parts.append(f"year-to-year revenue variation (coefficient of variation) is {_signed(cv)}")
    if hhi:
        parts.append(f"the revenue concentration index is {_signed(hhi)}, where 100% means a single source")
    gaps = [label for m, label in ((cagr, "revenue growth"), (cv, "revenue volatility"),
                                   (hhi, "revenue concentration")) if m is None]
    note = f"{_join(gaps)} could not be computed from the filings" if gaps else ""
    return d.result("revenue_resilience", weight, _sentence(parts, note))


def _cost_discipline(metrics: FinancialMetrics, weight: float) -> DimensionScore:
    d = _Dim(metrics)
    officer, fees = d.get("officer_comp_share"), d.get("pro_fundraising_fee_share")
    exp_g, rev_g = d.get("expense_cagr_3y"), d.get("revenue_cagr_3y")
    for m in (officer, fees):
        if m is not None:
            d.subscores.append(interpolate(m.value, RUBRIC[m.key]))
    if exp_g and rev_g:
        d.subscores.append(interpolate(exp_g.value - rev_g.value, RUBRIC["expense_growth_gap"]))
    else:
        unused = {m.evidence_id for m in (exp_g, rev_g) if m is not None}
        d.drivers = [i for i in d.drivers if i not in unused]

    parts = []
    if officer:
        parts.append(f"officer compensation is {_signed(officer)} of expenses")
    if fees:
        parts.append(f"professional fundraising fees are {_signed(fees)} of contributions")
    if exp_g and rev_g:
        parts.append(f"expenses {_growth(exp_g)} a year while revenue {_growth(rev_g)} a year")
    gaps = [label for ok, label in ((officer, "officer compensation share"),
                                    (fees, "professional fundraising fee share"),
                                    (exp_g and rev_g, "expense growth versus revenue growth")) if not ok]
    note = f"{_join(gaps)} could not be computed from the filings" if gaps else ""
    return d.result("cost_discipline", weight, _sentence(parts, note))


def _transparency(metrics: FinancialMetrics, impact: ImpactAssessment | None, weight: float) -> DimensionScore:
    d = _Dim(metrics)
    recency, count = d.get("filing_recency_years"), d.get("years_of_filings")
    for m in (recency, count):
        if m is not None:
            d.subscores.append(interpolate(m.value, RUBRIC[m.key]))

    parts = []
    if recency:
        year = f"FY{recency.tax_year} " if recency.tax_year else ""
        parts.append(f"the latest filing with data is {year}({_years(recency.value)} ago)")
    if count:
        verb = "is" if count.value == 1 else "are"
        parts.append(f"{_years(count.value)} of filings {verb} in the IRS extract")

    if impact is None:
        d.missing += ["publishes_financials", "publishes_outcomes"]
        parts.append("the charity's website was not reviewed")
    else:
        used_web = False
        for attr, noun in (("publishes_financials", "financial reports"), ("publishes_outcomes", "outcome data")):
            flag = getattr(impact, attr)
            if flag is None:
                d.missing.append(attr)
                parts.append(f"the review could not tell whether the website publishes {noun}")
                continue
            used_web = True
            d.subscores.append(100.0 if flag else 0.0)
            parts.append(f"the website {'publishes' if flag else 'does not publish'} {noun}")
        if used_web:
            d.drivers += impact.evidence_ids
    return d.result("transparency", weight, _sentence(parts))


def _impact_evidence(impact: ImpactAssessment | None, weight: float) -> DimensionScore:
    if impact is None:
        return DimensionScore(
            dimension="impact_evidence",
            label=DIMENSION_LABELS["impact_evidence"],
            score=None,
            weight=weight,
            explanation="No impact assessment is available, so this dimension is not scored.",
            missing_inputs=["impact_assessment"],
        )
    if not impact.pages_read and not impact.evidence_ids:
        # A blocked or unreachable website says nothing about the charity's results, so it is not scored as 0.
        return DimensionScore(
            dimension="impact_evidence",
            label=DIMENSION_LABELS["impact_evidence"],
            score=None,
            weight=weight,
            explanation="The charity's website could not be read in this run, so impact evidence is not scored. "
            "Ask the charity for its outcome reports.",
            missing_inputs=["website_content"],
        )
    level = max(0, min(4, int(impact.evidence_level)))
    label = impact.evidence_level_label or IMPACT_EVIDENCE_LEVELS[level]
    return DimensionScore(
        dimension="impact_evidence",
        label=DIMENSION_LABELS["impact_evidence"],
        score=float(level * 25),
        weight=weight,
        drivers=list(dict.fromkeys(impact.evidence_ids)),
        explanation=f"The impact review rated the evidence at level {level} of 4: {label[:1].lower() + label[1:]}.",
    )


def _weights(weights: Weights) -> dict[str, float]:
    raw = {dim: float(getattr(weights, dim)) for dim in DIMENSIONS}
    if all(w == 0 for w in raw.values()):
        return {dim: 1.0 for dim in DIMENSIONS}
    return raw


def band_for(overall: float | None, none_count: int, has_filings: bool) -> str:
    if not has_filings or none_count >= 2 or overall is None:
        return "insufficient_data"
    if overall >= BAND_STRONG:
        return "strong_fit"
    if overall >= BAND_FIT:
        return "fit_with_questions"
    return "weak_fit"


def score_charity(
    profile: OrgProfile,
    metrics: FinancialMetrics,
    impact: ImpactAssessment | None,
    weights: Weights,
) -> CharityScorecard:
    w = _weights(weights)
    dims = [
        _financial_health(metrics, w["financial_health"]),
        _revenue_resilience(metrics, w["revenue_resilience"]),
        _cost_discipline(metrics, w["cost_discipline"]),
        _transparency(metrics, impact, w["transparency"]),
        _impact_evidence(impact, w["impact_evidence"]),
    ]
    scored = [d for d in dims if d.score is not None]
    total_weight = sum(d.weight for d in scored)
    overall = round(sum(d.score * d.weight for d in scored) / total_weight, 1) if total_weight > 0 else None
    none_count = len(dims) - len(scored)
    return CharityScorecard(
        ein=profile.ein,
        name=profile.name,
        is_demo=profile.is_demo,
        dimensions=dims,
        overall=overall,
        band=band_for(overall, none_count, bool(profile.filings)),  # type: ignore[arg-type]
    )
