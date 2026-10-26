"""Deterministic financial evidence and metrics (owner: data and scoring builder).

No LLM calls here. Every metric is reproducible from the OrgProfile.
Metric keys and formulas are fixed in docs/contract.md section 4 (helpers in section 12.3).
"""

from __future__ import annotations

import math
import statistics
from datetime import date
from typing import Any

from app.schemas import Evidence, FilingYear, FinancialMetrics, Metric, OrgProfile, Unit
from app.tools.propublica import MONEY_FIELDS, org_page_url, raw_source_for

FIELD_LABELS: dict[str, str] = {
    "total_revenue": "Total revenue",
    "total_expenses": "Total expenses",
    "total_assets": "Total assets (end of year)",
    "total_liabilities": "Total liabilities (end of year)",
    "net_assets": "Net assets (end of year)",
    "contributions": "Contributions and grants",
    "program_service_revenue": "Program service revenue",
    "investment_income": "Investment income",
    "officer_compensation": "Compensation of current officers and key employees",
    "other_salaries": "Other salaries and wages",
    "payroll_tax": "Payroll taxes",
    "professional_fundraising_fees": "Professional fundraising fees",
    "fundraising_event_gross": "Fundraising events gross income",
    "fundraising_event_direct_expenses": "Fundraising events direct expenses",
}

# key -> (label, unit), in display order.
METRIC_INFO: dict[str, tuple[str, Unit]] = {
    "total_revenue_latest": ("Total revenue (latest year)", "usd"),
    "total_expenses_latest": ("Total expenses (latest year)", "usd"),
    "surplus_margin": ("Surplus margin (latest year)", "ratio"),
    "avg_surplus_margin_3y": ("Average surplus margin (up to 3 latest years)", "ratio"),
    "net_assets_months": ("Reserves proxy (net assets in months of expenses)", "months"),
    "liabilities_to_assets": ("Liabilities to assets", "ratio"),
    "revenue_cagr_3y": ("Revenue growth per year (about 3 years)", "ratio"),
    "expense_cagr_3y": ("Expense growth per year (about 3 years)", "ratio"),
    "revenue_volatility_cv": ("Revenue volatility (coefficient of variation, up to 5 years)", "ratio"),
    "contributions_share": ("Contributions and grants as a share of revenue", "ratio"),
    "revenue_concentration_hhi": ("Revenue concentration index (HHI across 4 sources)", "ratio"),
    "officer_comp_share": ("Officer compensation as a share of expenses", "ratio"),
    "staff_cost_share": ("Staff costs as a share of expenses (officers, salaries, payroll tax)", "ratio"),
    "pro_fundraising_fee_share": ("Professional fundraising fees as a share of contributions", "ratio"),
    "filing_recency_years": ("Years since the latest filing with data", "years"),
    "years_of_filings": ("Years of filings with data", "count"),
    "program_expense_share": ("Program expense share", "ratio"),
}
METRIC_KEYS: tuple[str, ...] = tuple(METRIC_INFO)

FORMULAS: dict[str, str] = {
    "total_revenue_latest": "Total revenue from the latest filing with data.",
    "total_expenses_latest": "Total functional expenses from the latest filing with data.",
    "surplus_margin": "Total revenue minus total expenses, divided by total revenue, for the latest year.",
    "avg_surplus_margin_3y": "Mean of the yearly surplus margins over up to the 3 newest filings (needs at least 2).",
    "net_assets_months": (
        "Net assets divided by monthly expenses (total expenses / 12) for the latest year. This is a reserves "
        "proxy: net assets can include buildings and restricted funds that cannot pay for operations."
    ),
    "liabilities_to_assets": "Total liabilities divided by total assets for the latest year.",
    "revenue_cagr_3y": (
        "Compound annual growth of total revenue since the filing about 3 years before the latest one: "
        "(latest / earlier) to the power 1/years, minus 1."
    ),
    "expense_cagr_3y": (
        "Compound annual growth of total expenses since the filing about 3 years before the latest one: "
        "(latest / earlier) to the power 1/years, minus 1."
    ),
    "revenue_volatility_cv": (
        "Sample standard deviation of total revenue divided by its mean, over up to the 5 newest filings "
        "(needs at least 3)."
    ),
    "contributions_share": "Contributions and grants divided by total revenue for the latest year.",
    "revenue_concentration_hhi": (
        "Sum of squared shares of four revenue sources (contributions, program service revenue, investment "
        "income, other) for the latest year. Negative sources count as 0. 1.0 means a single source."
    ),
    "officer_comp_share": "Compensation of current officers and key employees divided by total expenses, latest year.",
    "staff_cost_share": (
        "Officer compensation plus other salaries and wages plus payroll taxes, divided by total expenses, latest year."
    ),
    "pro_fundraising_fee_share": "Professional fundraising fees divided by contributions and grants, latest year.",
    "filing_recency_years": "Current calendar year minus the tax year of the latest filing with data.",
    "years_of_filings": "Number of tax years with Form 990 data in the ProPublica extract.",
    "program_expense_share": "Program service expenses divided by total expenses.",
}

PROGRAM_EXPENSE_REASON = (
    "Not in the free IRS extract (Form 990 Part IX, column B). Ask the charity or read the filing PDF."
)
NO_FILINGS_REASON = "No filings with financial data in the ProPublica extract."
CAGR_GAP_PREFERENCE: tuple[int, ...] = (3, 2, 4)


# --------------------------------------------------------------------------- ids and formatting


def pp_id(ein: str, tax_year: int, field: str) -> str:
    return f"PP-{ein}-{tax_year}-{field}"


def calc_id(ein: str, key: str) -> str:
    return f"CALC-{ein}-{key}"


def _plain_number(v: float) -> str:
    if abs(v - round(v)) < 1e-9:
        return f"{round(v):,}"
    return f"{v:,.1f}"


def _format_usd(v: float) -> str:
    a = abs(v)
    if a < 100_000:
        body = f"{a:,.0f}"
    elif a < 999_500:
        body = f"{a / 1e3:.0f}K"
    elif a < 999_950_000:
        body = f"{a / 1e6:.1f}M"
    else:
        body = f"{a / 1e9:.2f}B"
    sign = "-" if v < 0 and body.strip("0.,KMB") else ""
    return f"{sign}${body}"


def format_value(value: float | None, unit: str) -> str:
    """Display string: usd $3.22B / $41.5M / $812K / $9,450; ratio 12.4%; months 7.1 months; None n/a."""
    if value is None or isinstance(value, bool):
        return "n/a"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(v) or math.isinf(v):
        return "n/a"
    if unit == "usd":
        return _format_usd(v)
    if unit == "ratio":
        pct = round(v * 100, 1)
        return f"{0.0 if pct == 0 else pct:.1f}%"
    if unit == "months":
        months = round(v, 1)
        return f"{0.0 if months == 0 else months:.1f} months"
    return _plain_number(v)


def _usd_exact(v: float) -> str:
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


def _signed_pct(v: float) -> str:
    text = format_value(v, "ratio")
    return text if text.startswith("-") else f"+{text}"


def _form_label(form_type: str | None) -> str:
    return f"Form {form_type}" if form_type else "Form 990 extract"


def evidence_source_url(profile: OrgProfile) -> str:
    """Human-readable source for IRS evidence: the ProPublica page, or the fixture for DEMO data."""
    if profile.is_demo:
        return profile.source_url
    try:
        return org_page_url(profile.ein)
    except ValueError:
        return profile.source_url


# --------------------------------------------------------------------------- IRS field evidence


def build_irs_evidence(profile: OrgProfile) -> dict[str, Evidence]:
    """One Evidence entry (kind="irs_field", id PP-<ein>-<year>-<field>) per non-null FilingYear field."""
    source = evidence_source_url(profile)
    out: dict[str, Evidence] = {}
    for filing in profile.filings:
        form = _form_label(filing.form_type)
        for field in MONEY_FIELDS:
            value = getattr(filing, field)
            if value is None:
                continue
            eid = pp_id(profile.ein, filing.tax_year, field)
            raw_keys = " + ".join(raw_source_for(filing.form_type, field)) or field
            period = f", tax period {filing.tax_period}" if filing.tax_period else ""
            out[eid] = Evidence(
                id=eid,
                kind="irs_field",
                ein=profile.ein,
                label=f"{FIELD_LABELS[field]}, FY{filing.tax_year} ({form})",
                value=float(value),
                unit="usd",
                display=format_value(value, "usd"),
                source_url=source,
                excerpt=f"ProPublica {form} extract{period}: {raw_keys} = {_usd_exact(value)}.",
                tax_year=filing.tax_year,
            )
    return out


# --------------------------------------------------------------------------- metrics


def _missing(filing: FilingYear, field: str) -> str:
    return f"The FY{filing.tax_year} filing ({_form_label(filing.form_type)}) has no value for {FIELD_LABELS[field].lower()}."


def _margin(filing: FilingYear) -> tuple[float | None, str | None]:
    rev, exp = filing.total_revenue, filing.total_expenses
    if rev is None:
        return None, _missing(filing, "total_revenue")
    if exp is None:
        return None, _missing(filing, "total_expenses")
    if rev <= 0:
        return None, f"Total revenue is {_usd_exact(rev)} in FY{filing.tax_year}, so a margin is undefined."
    return (rev - exp) / rev, None


class _MetricBuilder:
    def __init__(self, profile: OrgProfile) -> None:
        self.ein = profile.ein
        self.source = evidence_source_url(profile)
        self.metrics: dict[str, Metric] = {}
        self.evidence: dict[str, Evidence] = {}

    def pid(self, filing: FilingYear, field: str) -> str:
        return pp_id(self.ein, filing.tax_year, field)

    def put(
        self,
        key: str,
        value: float | None,
        *,
        inputs: list[str] | None = None,
        detail: str = "",
        reason: str | None = None,
        tax_year: int | None = None,
    ) -> None:
        label, unit = METRIC_INFO[key]
        if value is not None and (math.isnan(value) or math.isinf(value)):
            value, reason = None, "The calculation did not produce a finite number."
        if value is None:
            reason = reason or "Not enough data to compute this metric."
            excerpt = f"{FORMULAS[key]} Not computed: {reason}"
        else:
            reason = None
            excerpt = f"{FORMULAS[key]} {detail}".strip()
        display = format_value(value, unit)
        eid = calc_id(self.ein, key)
        self.evidence[eid] = Evidence(
            id=eid,
            kind="calculation",
            ein=self.ein,
            label=label,
            value=value,
            unit=unit,
            display=display,
            source_url=self.source,
            excerpt=excerpt,
            inputs=list(dict.fromkeys(inputs or [])),
            tax_year=tax_year,
        )
        self.metrics[key] = Metric(
            key=key,
            label=label,
            value=value,
            unit=unit,
            display=display,
            evidence_id=eid,
            reason_missing=reason,
            tax_year=tax_year,
        )

    def ratio(
        self,
        key: str,
        filing: FilingYear,
        num_fields: tuple[str, ...],
        den_field: str,
        num_words: str,
    ) -> None:
        """Latest-year ratio: sum(num_fields) / den_field, None when any input is missing or den <= 0."""
        year = filing.tax_year
        for field in (*num_fields, den_field):
            if getattr(filing, field) is None:
                self.put(key, None, reason=_missing(filing, field), tax_year=year)
                return
        den = getattr(filing, den_field)
        if den <= 0:
            reason = f"{FIELD_LABELS[den_field]} is {_usd_exact(den)} in FY{year}, so the ratio is undefined."
            self.put(key, None, reason=reason, tax_year=year)
            return
        num = sum(getattr(filing, f) for f in num_fields)
        value = num / den
        parts = " + ".join(f"{FIELD_LABELS[f].lower()} {_usd_exact(getattr(filing, f))}" for f in num_fields)
        detail = (
            f"FY{year}: {parts} = {_usd_exact(num)} {num_words}, divided by {FIELD_LABELS[den_field].lower()} "
            f"{_usd_exact(den)} = {format_value(value, 'ratio')}."
            if len(num_fields) > 1
            else f"FY{year}: {parts}, divided by {FIELD_LABELS[den_field].lower()} {_usd_exact(den)} = "
            f"{format_value(value, 'ratio')}."
        )
        inputs = [self.pid(filing, f) for f in (*num_fields, den_field)]
        self.put(key, value, inputs=inputs, detail=detail, tax_year=year)

    def cagr(self, key: str, filings: list[FilingYear], field: str) -> None:
        latest = filings[0]
        year = latest.tax_year
        label = FIELD_LABELS[field].lower()
        end = getattr(latest, field)
        if end is None:
            self.put(key, None, reason=_missing(latest, field), tax_year=year)
            return
        by_year = {f.tax_year: f for f in filings}
        base: FilingYear | None = None
        gap = 0
        for k in CAGR_GAP_PREFERENCE:
            cand = by_year.get(year - k)
            if cand is not None and getattr(cand, field) is not None:
                base, gap = cand, k
                break
        if base is None:
            reason = f"Needs {label} from a filing 2 to 4 years before FY{year}; none is available."
            self.put(key, None, reason=reason, tax_year=year)
            return
        start = getattr(base, field)
        if start <= 0 or end <= 0:
            reason = (
                f"Growth is undefined when {label} is zero or negative "
                f"(FY{base.tax_year} {_usd_exact(start)}, FY{year} {_usd_exact(end)})."
            )
            self.put(key, None, reason=reason, tax_year=year)
            return
        value = (end / start) ** (1 / gap) - 1
        detail = (
            f"{FIELD_LABELS[field]} went from {_usd_exact(start)} in FY{base.tax_year} to {_usd_exact(end)} in "
            f"FY{year} over {gap} years: ({_usd_exact(end)} / {_usd_exact(start)}) to the power 1/{gap}, "
            f"minus 1 = {format_value(value, 'ratio')} per year."
        )
        inputs = [self.pid(base, field), self.pid(latest, field)]
        self.put(key, value, inputs=inputs, detail=detail, tax_year=year)


def _any_field_id(builder: _MetricBuilder, filing: FilingYear) -> list[str]:
    for field in MONEY_FIELDS:
        if getattr(filing, field) is not None:
            return [builder.pid(filing, field)]
    return []


def compute_metrics(
    profile: OrgProfile, *, today: date | None = None
) -> tuple[FinancialMetrics, dict[str, Evidence]]:
    """Return metrics plus CALC-<ein>-<metric_key> evidence entries (with inputs = PP ids used).

    Every metric key gets a CALC entry, including missing ones (value None, excerpt states why), so agents can
    cite a gap. `today` is injectable for tests (filing_recency_years)."""
    b = _MetricBuilder(profile)
    filings = profile.filings
    current_year = (today or date.today()).year

    if not filings:
        for key in METRIC_KEYS:
            if key == "years_of_filings":
                b.put(key, 0.0, detail="No tax years with Form 990 data in the ProPublica extract (0).")
            elif key == "program_expense_share":
                b.put(key, None, reason=PROGRAM_EXPENSE_REASON)
            else:
                b.put(key, None, reason=NO_FILINGS_REASON)
        return FinancialMetrics(ein=profile.ein, latest_tax_year=None, years_of_data=0, metrics=b.metrics), b.evidence

    latest = filings[0]
    year = latest.tax_year

    for key, field in (("total_revenue_latest", "total_revenue"), ("total_expenses_latest", "total_expenses")):
        value = getattr(latest, field)
        if value is None:
            b.put(key, None, reason=_missing(latest, field), tax_year=year)
        else:
            detail = f"FY{year}: {FIELD_LABELS[field].lower()} {_usd_exact(value)}."
            b.put(key, value, inputs=[b.pid(latest, field)], detail=detail, tax_year=year)

    margin, reason = _margin(latest)
    if margin is None:
        b.put("surplus_margin", None, reason=reason, tax_year=year)
    else:
        detail = (
            f"FY{year}: total revenue {_usd_exact(latest.total_revenue)} minus total expenses "
            f"{_usd_exact(latest.total_expenses)}, divided by total revenue = {format_value(margin, 'ratio')}."
        )
        inputs = [b.pid(latest, "total_revenue"), b.pid(latest, "total_expenses")]
        b.put("surplus_margin", margin, inputs=inputs, detail=detail, tax_year=year)

    recent = [(f, m) for f in filings[:3] if (m := _margin(f)[0]) is not None]
    if len(recent) < 2:
        reason = f"Needs surplus margins for at least 2 of the 3 newest filings; {len(recent)} available."
        b.put("avg_surplus_margin_3y", None, reason=reason, tax_year=year)
    else:
        avg = statistics.fmean(m for _, m in recent)
        listed = ", ".join(f"FY{f.tax_year} {format_value(m, 'ratio')}" for f, m in recent)
        inputs = [b.pid(f, fld) for f, _ in recent for fld in ("total_revenue", "total_expenses")]
        detail = f"Mean of {listed} = {format_value(avg, 'ratio')}."
        b.put("avg_surplus_margin_3y", avg, inputs=inputs, detail=detail, tax_year=year)

    na, exp = latest.net_assets, latest.total_expenses
    if na is None or exp is None:
        b.put("net_assets_months", None, reason=_missing(latest, "net_assets" if na is None else "total_expenses"),
              tax_year=year)
    elif exp <= 0:
        reason = f"Total expenses are {_usd_exact(exp)} in FY{year}, so months of expenses are undefined."
        b.put("net_assets_months", None, reason=reason, tax_year=year)
    else:
        months = na / (exp / 12)
        detail = (
            f"FY{year}: net assets {_usd_exact(na)} divided by monthly expenses ({_usd_exact(exp)} / 12 = "
            f"{_usd_exact(exp / 12)}) = {format_value(months, 'months')}."
        )
        inputs = [b.pid(latest, "net_assets"), b.pid(latest, "total_expenses")]
        b.put("net_assets_months", months, inputs=inputs, detail=detail, tax_year=year)

    b.ratio("liabilities_to_assets", latest, ("total_liabilities",), "total_assets", "")
    b.cagr("revenue_cagr_3y", filings, "total_revenue")
    b.cagr("expense_cagr_3y", filings, "total_expenses")

    revs = [(f, f.total_revenue) for f in filings if f.total_revenue is not None][:5]
    if len(revs) < 3:
        b.put("revenue_volatility_cv", None,
              reason=f"Needs total revenue for at least 3 filings; {len(revs)} available.", tax_year=year)
    else:
        values = [v for _, v in revs]
        mean = statistics.fmean(values)
        if mean <= 0:
            b.put("revenue_volatility_cv", None, reason="Mean revenue is zero or negative.", tax_year=year)
        else:
            sd = statistics.stdev(values)
            cv = sd / mean
            years_txt = f"FY{revs[-1][0].tax_year} to FY{revs[0][0].tax_year}"
            detail = (
                f"Total revenue for {years_txt} ({len(revs)} filings): standard deviation {_usd_exact(sd)} "
                f"divided by mean {_usd_exact(mean)} = {format_value(cv, 'ratio')}."
            )
            inputs = [b.pid(f, "total_revenue") for f, _ in revs]
            b.put("revenue_volatility_cv", cv, inputs=inputs, detail=detail, tax_year=year)

    b.ratio("contributions_share", latest, ("contributions",), "total_revenue", "")
    _hhi(b, latest)
    b.ratio("officer_comp_share", latest, ("officer_compensation",), "total_expenses", "")
    b.ratio("staff_cost_share", latest, ("officer_compensation", "other_salaries", "payroll_tax"),
            "total_expenses", "in staff costs")
    b.ratio("pro_fundraising_fee_share", latest, ("professional_fundraising_fees",), "contributions", "")

    recency = float(current_year - year)
    b.put("filing_recency_years", recency, inputs=_any_field_id(b, latest),
          detail=f"{current_year} minus FY{year} = {_plain_number(recency)}.", tax_year=year)

    count_inputs = [i for f in filings for i in _any_field_id(b, f)]
    years_txt = ", ".join(str(f.tax_year) for f in filings)
    b.put("years_of_filings", float(len(filings)), inputs=count_inputs,
          detail=f"Tax years with data: {years_txt} ({len(filings)}).", tax_year=year)

    b.put("program_expense_share", None, reason=PROGRAM_EXPENSE_REASON, tax_year=year)

    metrics = FinancialMetrics(
        ein=profile.ein, latest_tax_year=year, years_of_data=len(filings), metrics=b.metrics
    )
    return metrics, b.evidence


def _hhi(b: _MetricBuilder, latest: FilingYear) -> None:
    key, year = "revenue_concentration_hhi", latest.tax_year
    fields = ("total_revenue", "contributions", "program_service_revenue", "investment_income")
    for field in fields:
        if getattr(latest, field) is None:
            b.put(key, None, reason=_missing(latest, field), tax_year=year)
            return
    rev = latest.total_revenue
    if rev <= 0:
        b.put(key, None, reason=f"Total revenue is {_usd_exact(rev)} in FY{year}, so shares are undefined.",
              tax_year=year)
        return
    con, prog, inv = latest.contributions, latest.program_service_revenue, latest.investment_income
    parts = {
        "contributions": max(con, 0.0),
        "program service revenue": max(prog, 0.0),
        "investment income": max(inv, 0.0),
        "other revenue": max(rev - con - prog - inv, 0.0),
    }
    total = sum(parts.values())
    if total <= 0:
        b.put(key, None, reason=f"No positive revenue sources in FY{year}.", tax_year=year)
        return
    shares = {name: amount / total for name, amount in parts.items()}
    hhi = sum(s * s for s in shares.values())
    listed = ", ".join(f"{name} {format_value(s, 'ratio')}" for name, s in shares.items())
    detail = f"FY{year} shares: {listed}. Sum of squared shares = {hhi:.3f}."
    b.put(key, hhi, inputs=[b.pid(latest, f) for f in fields], detail=detail, tax_year=year)


# --------------------------------------------------------------------------- agent helpers


def field_history(profile: OrgProfile, field: str, years: int = 5) -> list[dict[str, Any]]:
    """[{tax_year, value, evidence_id, display, form_type}] newest first, for the financial agent's tool.
    Unknown fields return []. Missing values have value None and evidence_id None."""
    if field not in MONEY_FIELDS:
        return []
    out = []
    for filing in profile.filings[: max(1, int(years))]:
        value = getattr(filing, field)
        out.append(
            {
                "tax_year": filing.tax_year,
                "value": value,
                "evidence_id": pp_id(profile.ein, filing.tax_year, field) if value is not None else None,
                "display": format_value(value, "usd"),
                "form_type": filing.form_type,
            }
        )
    return out


def compare_years(profile: OrgProfile, field: str, year_a: int, year_b: int) -> Evidence | None:
    """Percent change in one FilingYear field from year_a (base) to year_b.
    None when the field is unknown, either value is missing, or the base is <= 0."""
    if field not in MONEY_FIELDS:
        return None
    by_year = {f.tax_year: f for f in profile.filings}
    fa, fb = by_year.get(int(year_a)), by_year.get(int(year_b))
    if fa is None or fb is None:
        return None
    va, vb = getattr(fa, field), getattr(fb, field)
    if va is None or vb is None or va <= 0:
        return None
    change = (vb - va) / va
    label = FIELD_LABELS[field]
    return Evidence(
        id=f"CALC-{profile.ein}-{field}-chg-{fa.tax_year}-{fb.tax_year}",
        kind="calculation",
        ein=profile.ein,
        label=f"Change in {label.lower()}, FY{fa.tax_year} to FY{fb.tax_year}",
        value=change,
        unit="ratio",
        display=f"{_signed_pct(change)} ({fa.tax_year} to {fb.tax_year})",
        source_url=evidence_source_url(profile),
        excerpt=(
            f"{label} FY{fb.tax_year} {_usd_exact(vb)} minus FY{fa.tax_year} {_usd_exact(va)}, divided by "
            f"FY{fa.tax_year} {_usd_exact(va)} = {_signed_pct(change)}."
        ),
        inputs=[pp_id(profile.ein, fa.tax_year, field), pp_id(profile.ein, fb.tax_year, field)],
        tax_year=fb.tax_year,
    )
