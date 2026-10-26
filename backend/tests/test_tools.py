"""Offline tests for app.tools: ProPublica mapping, metrics, scoring, and web access."""

from __future__ import annotations

import json
from datetime import date

import pytest

from app.schemas import (
    DIMENSIONS,
    FilingYear,
    FinancialMetrics,
    ImpactAssessment,
    Metric,
    OrgProfile,
    Weights,
)
from app.tools import financials, propublica, scoring, web
from app.tools.financials import (
    METRIC_KEYS,
    PROGRAM_EXPENSE_REASON,
    build_irs_evidence,
    compare_years,
    compute_metrics,
    field_history,
    format_value,
)
from app.tools.propublica import CACHE_DIR, FEATURED_EINS, list_featured_orgs, load_cached_profile
from app.tools.scoring import interpolate, score_charity

TODAY = date(2026, 10, 26)
FOODSHARE = "061063025"  # Form 990
GARDEN_CLUB = "061527913"  # Form 990EZ
FOUNDATION = "061603158"  # Form 990PF
EM_DASH = chr(0x2014)


def _profile(filings: list[FilingYear], ein: str = "123456789") -> OrgProfile:
    return OrgProfile(
        ein=ein,
        name="Test Org",
        source_url=propublica.org_api_url(ein),
        filings=sorted(filings, key=lambda f: f.tax_year, reverse=True),
        fetched_at="2026-10-26T00:00:00+00:00",
    )


def _filing(year: int, **values) -> FilingYear:
    base = dict(
        total_revenue=1_000_000.0,
        total_expenses=950_000.0,
        total_assets=600_000.0,
        total_liabilities=100_000.0,
        net_assets=500_000.0,
        contributions=900_000.0,
        program_service_revenue=50_000.0,
        investment_income=10_000.0,
        officer_compensation=80_000.0,
        other_salaries=300_000.0,
        payroll_tax=30_000.0,
        professional_fundraising_fees=0.0,
    )
    base.update(values)
    return FilingYear(tax_year=year, tax_period=year * 100 + 12, form_type="990", **base)


# --------------------------------------------------------------------------- ProPublica mapping and cache


def test_map_form_990_matches_raw_json():
    raw = json.loads((CACHE_DIR / f"org_{FOODSHARE}.json").read_text(encoding="utf-8"))
    raw_2024 = next(f for f in raw["filings_with_data"] if f["tax_prd_yr"] == 2024)
    filing = load_cached_profile(FOODSHARE).filings[0]
    assert filing.tax_year == 2024 and filing.tax_period == 202406 and filing.form_type == "990"
    assert filing.total_revenue == raw_2024["totrevenue"] == 120_231_966
    assert filing.total_expenses == raw_2024["totfuncexpns"] == 122_870_455
    assert filing.net_assets == raw_2024["totnetassetend"] == 52_600_634
    assert filing.contributions == raw_2024["totcntrbgfts"]
    assert filing.officer_compensation == raw_2024["compnsatncurrofcr"]
    assert filing.professional_fundraising_fees == raw_2024["profndraising"]
    assert filing.pdf_url and filing.pdf_url.startswith("https://projects.propublica.org/")


def test_map_form_990ez():
    filing = load_cached_profile(GARDEN_CLUB).filings[0]
    assert filing.form_type == "990EZ" and filing.tax_year == 2023
    assert filing.total_revenue == 35_162
    assert filing.net_assets == 97_356  # totnetassetsend
    assert filing.contributions == 10_650  # totcntrbs
    assert filing.program_service_revenue == 2_776  # prgmservrev
    assert filing.investment_income == 16  # othrinvstinc
    # 990EZ has no officer, salary, payroll-tax or professional-fundraising lines: None, never 0.
    assert filing.officer_compensation is None
    assert filing.other_salaries is None
    assert filing.payroll_tax is None
    assert filing.professional_fundraising_fees is None


def test_map_form_990pf():
    filing = load_cached_profile(FOUNDATION).filings[0]
    assert filing.form_type == "990PF" and filing.tax_year == 2023
    assert filing.total_revenue == 15_475_263
    assert filing.net_assets == 265_182_093  # tfundnworth
    assert filing.contributions == 2_093_450  # grscontrgifts
    assert filing.investment_income == 12_824  # intrstrvnue 12824 + dividndsamt 0
    assert filing.officer_compensation == 0  # compofficers reported as 0
    assert filing.program_service_revenue is None
    assert filing.other_salaries is None


def test_cache_files_have_cache_metadata():
    paths = sorted(CACHE_DIR.glob("org_*.json"))
    assert len(paths) >= 7
    assert not (CACHE_DIR / "_probe").exists()
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        ein = path.stem.removeprefix("org_")
        assert raw["_cache"]["source_url"] == propublica.org_api_url(ein)
        assert raw["_cache"]["fetched_at"]


def test_featured_list_offline_demo_first():
    results = list_featured_orgs()
    eins = [r.ein for r in results]
    assert eins == ["000000001", "000000002", *FEATURED_EINS]
    assert [r.is_demo for r in results[:2]] == [True, True]
    assert not any(r.is_demo for r in results[2:])
    assert all(r.latest_revenue for r in results)


async def test_get_org_profile_offline_uses_cache_and_rejects_unknown():
    profile = await propublica.get_org_profile(FOODSHARE)
    assert profile.from_cache and profile.name == "Connecticut Foodshare Inc"
    with pytest.raises(propublica.OrgNotFound):
        await propublica.get_org_profile("999999999")


# --------------------------------------------------------------------------- demo fixtures


@pytest.mark.parametrize(
    "ein,name,website",
    [
        ("000000001", "Riverbend Community Pantry (DEMO)", "http://127.0.0.1:8000/demo/riverbend-pantry.html"),
        ("000000002", "Harbor Lights Literacy Project (DEMO)", "http://127.0.0.1:8000/demo/harbor-literacy.html"),
    ],
)
async def test_demo_fixture_loads_and_is_consistent(ein, name, website):
    profile = await propublica.get_org_profile(ein)
    assert profile.is_demo and profile.name == name and profile.website_url == website
    assert profile.state == "CT" and profile.subsection_code == 3
    assert len(profile.filings) >= 3
    for f in profile.filings:
        assert f.form_type == "990" and f.pdf_url is None
        assert f.net_assets == f.total_assets - f.total_liabilities
        assert f.officer_compensation + f.other_salaries + f.payroll_tax < f.total_expenses
        assert f.contributions + f.program_service_revenue + f.investment_income <= f.total_revenue
    raw = json.loads((CACHE_DIR / f"demo_{ein}.json").read_text(encoding="utf-8"))
    assert raw["_demo"]["note"] == "Fictional organization for testing. Not a real charity."


def test_harbor_lights_has_exactly_one_deficit_year():
    profile = load_cached_profile("000000002")
    deficits = [f.tax_year for f in profile.filings if f.total_expenses > f.total_revenue]
    assert len(deficits) == 1


# --------------------------------------------------------------------------- IRS evidence


def test_build_irs_evidence_ids_labels_and_sources():
    profile = load_cached_profile(FOODSHARE)
    evidence = build_irs_evidence(profile)
    ev = evidence["PP-061063025-2024-total_revenue"]
    assert ev.kind == "irs_field" and ev.unit == "usd" and ev.tax_year == 2024
    assert ev.value == 120_231_966 and ev.display == "$120.2M"
    assert ev.label == "Total revenue, FY2024 (Form 990)"
    assert ev.source_url == "https://projects.propublica.org/nonprofits/organizations/61063025"
    assert "totrevenue" in ev.excerpt
    # One entry per non-null field only.
    ez = build_irs_evidence(load_cached_profile(GARDEN_CLUB))
    assert "PP-061527913-2023-total_revenue" in ez
    assert "PP-061527913-2023-officer_compensation" not in ez

    demo = build_irs_evidence(load_cached_profile("000000001"))
    assert all(e.source_url == "fixture:demo_000000001.json" for e in demo.values())


# --------------------------------------------------------------------------- metrics


def test_metrics_real_org_hand_checked():
    profile = load_cached_profile(FOODSHARE)
    metrics, evidence = compute_metrics(profile, today=TODAY)
    m = metrics.metrics
    assert set(m) == set(METRIC_KEYS) and len(METRIC_KEYS) == 17
    assert metrics.latest_tax_year == 2024 and metrics.years_of_data == len(profile.filings)

    # Raw JSON FY2024: totrevenue 120231966, totfuncexpns 122870455, totliabend 3842301,
    # totassetsend 56442935, totnetassetend 52600634. FY2021: totrevenue 78588911.
    assert m["surplus_margin"].value == pytest.approx((120_231_966 - 122_870_455) / 120_231_966)
    assert m["surplus_margin"].display == "-2.2%"
    assert m["liabilities_to_assets"].value == pytest.approx(3_842_301 / 56_442_935)
    assert m["net_assets_months"].value == pytest.approx(52_600_634 / (122_870_455 / 12))
    assert m["net_assets_months"].display == "5.1 months"
    assert m["revenue_cagr_3y"].value == pytest.approx((120_231_966 / 78_588_911) ** (1 / 3) - 1)
    assert m["filing_recency_years"].value == 2
    assert m["program_expense_share"].value is None
    assert m["program_expense_share"].reason_missing == PROGRAM_EXPENSE_REASON

    calc = evidence["CALC-061063025-liabilities_to_assets"]
    assert calc.kind == "calculation"
    assert calc.inputs == ["PP-061063025-2024-total_liabilities", "PP-061063025-2024-total_assets"]
    assert "$3,842,301" in calc.excerpt and "$56,442,935" in calc.excerpt


def test_every_calc_input_is_a_known_pp_id():
    for ein in ("000000001", "000000002", FOODSHARE, GARDEN_CLUB, FOUNDATION):
        profile = load_cached_profile(ein)
        pp = build_irs_evidence(profile)
        metrics, calc = compute_metrics(profile, today=TODAY)
        for key, metric in metrics.metrics.items():
            assert metric.evidence_id == f"CALC-{ein}-{key}"
            ev = calc[metric.evidence_id]
            assert ev.value == metric.value
            assert (metric.value is None) == (metric.reason_missing is not None)
            for input_id in ev.inputs:
                assert input_id in pp, (key, input_id)
            if metric.value is not None and key not in ("program_expense_share",):
                assert ev.inputs, key
            assert EM_DASH not in (ev.excerpt or "") + ev.label


def test_990ez_missing_fields_are_none_with_reason():
    metrics, _ = compute_metrics(load_cached_profile(GARDEN_CLUB), today=TODAY)
    m = metrics.metrics
    assert m["officer_comp_share"].value is None
    assert "990EZ" in m["officer_comp_share"].reason_missing
    assert m["staff_cost_share"].value is None
    assert m["pro_fundraising_fee_share"].value is None
    assert m["surplus_margin"].value == pytest.approx((35_162 - 39_576) / 35_162)


def test_zero_revenue_gives_none_not_zero():
    profile = _profile([_filing(2023, total_revenue=0.0, contributions=0.0), _filing(2022), _filing(2021)])
    m = compute_metrics(profile, today=TODAY)[0].metrics
    for key in ("surplus_margin", "contributions_share", "revenue_concentration_hhi", "pro_fundraising_fee_share",
                "revenue_cagr_3y"):
        assert m[key].value is None, key
        assert m[key].reason_missing, key
    assert m["total_revenue_latest"].value == 0.0  # a reported zero is a value, not a gap
    assert m["net_assets_months"].value is not None
    # Average margin uses the two remaining years.
    assert m["avg_surplus_margin_3y"].value == pytest.approx(0.05)


def test_missing_field_gives_none_with_reason():
    profile = _profile([_filing(2023, total_assets=None), _filing(2022)])
    m = compute_metrics(profile, today=TODAY)[0].metrics
    assert m["liabilities_to_assets"].value is None
    assert "total assets" in m["liabilities_to_assets"].reason_missing


def test_single_filing():
    profile = _profile([_filing(2023)])
    metrics, evidence = compute_metrics(profile, today=TODAY)
    m = metrics.metrics
    assert m["surplus_margin"].value == pytest.approx(0.05)
    for key in ("avg_surplus_margin_3y", "revenue_cagr_3y", "expense_cagr_3y", "revenue_volatility_cv"):
        assert m[key].value is None and m[key].reason_missing, key
    assert m["years_of_filings"].value == 1
    assert m["filing_recency_years"].value == 3
    assert len(evidence) == 17


def test_no_filings():
    metrics, evidence = compute_metrics(_profile([]), today=TODAY)
    assert metrics.latest_tax_year is None and metrics.years_of_data == 0
    assert metrics.metrics["years_of_filings"].value == 0
    assert all(
        metrics.metrics[k].value is None for k in METRIC_KEYS if k != "years_of_filings"
    )
    assert len(evidence) == 17


def test_cagr_uses_two_year_gap_when_three_years_missing():
    profile = _profile([_filing(2023, total_revenue=1_210_000.0), _filing(2021, total_revenue=1_000_000.0)])
    m = compute_metrics(profile, today=TODAY)[0].metrics
    assert m["revenue_cagr_3y"].value == pytest.approx(0.10)


def test_revenue_volatility_and_hhi():
    profile = _profile([_filing(2023, total_revenue=1_200_000.0), _filing(2022, total_revenue=1_000_000.0),
                        _filing(2021, total_revenue=800_000.0)])
    m = compute_metrics(profile, today=TODAY)[0].metrics
    assert m["revenue_volatility_cv"].value == pytest.approx(200_000 / 1_000_000)
    # FY2023: contributions 900K, program 50K, investment 10K, other 240K of 1.2M.
    shares = [900 / 1200, 50 / 1200, 10 / 1200, 240 / 1200]
    assert m["revenue_concentration_hhi"].value == pytest.approx(sum(s * s for s in shares))


def test_field_history():
    profile = load_cached_profile("000000001")
    rows = field_history(profile, "total_revenue", years=2)
    assert [r["tax_year"] for r in rows] == [2024, 2023]
    assert rows[0]["evidence_id"] == "PP-000000001-2024-total_revenue"
    assert rows[0]["value"] == 1_583_900 and rows[0]["display"] == "$1.6M"
    assert field_history(profile, "not_a_field") == []


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        (3_217_077_611, "usd", "$3.22B"),
        (41_500_000, "usd", "$41.5M"),
        (812_000, "usd", "$812K"),
        (9_450, "usd", "$9,450"),
        (-1_200_000, "usd", "-$1.2M"),
        (999_600, "usd", "$1.0M"),
        (0, "usd", "$0"),
        (0.124, "ratio", "12.4%"),
        (-0.022, "ratio", "-2.2%"),
        (-0.00001, "ratio", "0.0%"),
        (7.08, "months", "7.1 months"),
        (3, "years", "3"),
        (14, "count", "14"),
        (None, "usd", "n/a"),
        (None, "ratio", "n/a"),
    ],
)
def test_format_value(value, unit, expected):
    assert format_value(value, unit) == expected


def test_compare_years():
    profile = load_cached_profile("000000001")
    ev = compare_years(profile, "total_revenue", 2021, 2024)
    assert ev.id == "CALC-000000001-total_revenue-chg-2021-2024"
    assert ev.unit == "ratio" and ev.kind == "calculation"
    assert ev.value == pytest.approx(1_583_900 / 1_212_400 - 1)
    assert ev.display == "+30.6% (2021 to 2024)"
    assert ev.inputs == ["PP-000000001-2021-total_revenue", "PP-000000001-2024-total_revenue"]
    down = compare_years(profile, "total_revenue", 2024, 2021)
    assert down.display.startswith("-23.5%")
    assert compare_years(profile, "total_revenue", 2019, 2024) is None  # year not filed
    assert compare_years(profile, "professional_fundraising_fees", 2021, 2024) is None  # base is 0
    assert compare_years(profile, "bogus", 2021, 2024) is None
    ez = load_cached_profile(GARDEN_CLUB)
    assert compare_years(ez, "officer_compensation", 2022, 2023) is None  # missing value


# --------------------------------------------------------------------------- scoring


def _metrics(ein: str = "123456789", **values) -> FinancialMetrics:
    units = {k: u for k, (_, u) in financials.METRIC_INFO.items()}
    metrics = {
        key: Metric(key=key, label=key, value=values.get(key), unit=units[key],
                    evidence_id=f"CALC-{ein}-{key}", tax_year=2024)
        for key in METRIC_KEYS
    }
    return FinancialMetrics(ein=ein, latest_tax_year=2024, years_of_data=4, metrics=metrics)


STRONG = dict(
    surplus_margin=0.06, avg_surplus_margin_3y=0.05, net_assets_months=8.0, liabilities_to_assets=0.1,
    revenue_concentration_hhi=0.4, revenue_volatility_cv=0.04, revenue_cagr_3y=0.06, expense_cagr_3y=0.05,
    officer_comp_share=0.03, pro_fundraising_fee_share=0.0, filing_recency_years=2, years_of_filings=6,
)
WEAK = dict(
    surplus_margin=-0.15, avg_surplus_margin_3y=-0.12, net_assets_months=0.5, liabilities_to_assets=0.9,
    revenue_concentration_hhi=1.0, revenue_volatility_cv=0.5, revenue_cagr_3y=-0.15, expense_cagr_3y=0.05,
    officer_comp_share=0.35, pro_fundraising_fee_share=0.25, filing_recency_years=6, years_of_filings=1,
)

MIDDLE = dict(
    surplus_margin=0.0, avg_surplus_margin_3y=0.0, net_assets_months=3.5, liabilities_to_assets=0.5,
    revenue_concentration_hhi=0.7, revenue_volatility_cv=0.15, revenue_cagr_3y=0.0, expense_cagr_3y=0.0,
    officer_comp_share=0.15, pro_fundraising_fee_share=0.10, filing_recency_years=3, years_of_filings=3,
)


def _impact(level: int, financials_flag=True, outcomes_flag=True) -> ImpactAssessment:
    return ImpactAssessment(ein="123456789", evidence_level=level, publishes_financials=financials_flag,
                            publishes_outcomes=outcomes_flag, evidence_ids=["WEB-123456789-1"])


def test_interpolate():
    points = ((0.30, 100.0), (0.70, 0.0))
    assert interpolate(0.1, points) == 100
    assert interpolate(0.5, points) == pytest.approx(50)
    assert interpolate(0.9, points) == 0
    assert interpolate(4.5, scoring.RUBRIC["net_assets_months"]) == pytest.approx(70)


def test_scoring_bands():
    profile = _profile([_filing(2024)])
    strong = score_charity(profile, _metrics(**STRONG), _impact(4), Weights())
    assert strong.band == "strong_fit" and strong.overall == 100
    weak = score_charity(profile, _metrics(**WEAK), _impact(0, False, False), Weights())
    assert weak.band == "weak_fit" and weak.overall < 50
    middle = score_charity(profile, _metrics(**MIDDLE), _impact(2, True, False), Weights())
    assert middle.band == "fit_with_questions" and 50 <= middle.overall < 70
    # 70 exactly is strong_fit: three dimensions at 100, transparency 50, impact 0.
    edge = score_charity(profile, _metrics(**STRONG), _impact(0, False, False), Weights())
    assert edge.overall == 70 and edge.band == "strong_fit"


def test_scoring_dimension_details():
    profile = _profile([_filing(2024)])
    card = score_charity(profile, _metrics(**STRONG), _impact(3), Weights())
    dims = {d.dimension: d for d in card.dimensions}
    assert [d.dimension for d in card.dimensions] == DIMENSIONS
    fh = dims["financial_health"]
    assert set(fh.drivers) == {f"CALC-123456789-{k}" for k in
                               ("surplus_margin", "avg_surplus_margin_3y", "net_assets_months",
                                "liabilities_to_assets")}
    assert fh.missing_inputs == []
    assert "8.0 months" in fh.explanation and "10.0%" in fh.explanation
    assert dims["impact_evidence"].score == 75
    assert dims["impact_evidence"].drivers == ["WEB-123456789-1"]
    assert "WEB-123456789-1" in dims["transparency"].drivers
    for d in card.dimensions:
        assert d.explanation.endswith(".") and EM_DASH not in d.explanation
        assert d.explanation.count(". ") == 0  # one sentence


def test_scoring_missing_inputs_listed():
    profile = _profile([_filing(2024)])
    values = dict(STRONG, liabilities_to_assets=None, officer_comp_share=None)
    card = score_charity(profile, _metrics(**values), None, Weights())
    dims = {d.dimension: d for d in card.dimensions}
    assert "liabilities_to_assets" in dims["financial_health"].missing_inputs
    assert "officer_comp_share" in dims["cost_discipline"].missing_inputs
    assert "liabilities to assets could not be computed" in dims["financial_health"].explanation
    assert dims["impact_evidence"].score is None
    assert set(dims["transparency"].missing_inputs) == {"publishes_financials", "publishes_outcomes"}
    assert card.band != "insufficient_data"  # only one dimension is None


def test_scoring_weights():
    profile = _profile([_filing(2024)])
    metrics = _metrics(**dict(STRONG, net_assets_months=1.0, liabilities_to_assets=0.7))
    impact = _impact(4)
    equal = score_charity(profile, metrics, impact, Weights())
    zero = score_charity(profile, metrics, impact, Weights(financial_health=0, revenue_resilience=0,
                                                           cost_discipline=0, transparency=0, impact_evidence=0))
    assert zero.overall == equal.overall
    assert all(d.weight == 1.0 for d in zero.dimensions)
    only_fh = score_charity(profile, metrics, impact, Weights(financial_health=5, revenue_resilience=0,
                                                              cost_discipline=0, transparency=0, impact_evidence=0))
    fh_score = only_fh.dimensions[0].score
    assert only_fh.overall == fh_score and fh_score < equal.overall


def test_insufficient_data():
    profile = _profile([_filing(2024)])
    # Impact missing plus no revenue metrics: two dimensions are None.
    values = {k: v for k, v in STRONG.items()
              if k not in ("revenue_concentration_hhi", "revenue_volatility_cv", "revenue_cagr_3y")}
    card = score_charity(profile, _metrics(**values), None, Weights())
    assert card.band == "insufficient_data"
    assert sum(d.score is None for d in card.dimensions) == 2
    # No filings at all.
    empty = _profile([])
    metrics, _ = compute_metrics(empty, today=TODAY)
    assert score_charity(empty, metrics, _impact(4), Weights()).band == "insufficient_data"


def test_score_demo_fixtures_end_to_end():
    for ein in ("000000001", "000000002"):
        profile = load_cached_profile(ein)
        metrics, _ = compute_metrics(profile, today=TODAY)
        card = score_charity(profile, metrics, _impact(3), Weights())
        assert card.is_demo and card.band in ("strong_fit", "fit_with_questions")
        assert all(d.score is not None for d in card.dimensions)


# --------------------------------------------------------------------------- web


@pytest.fixture
def demo_dir(tmp_path, monkeypatch):
    pages = tmp_path / "demo_pages"
    pages.mkdir()
    (pages / "riverbend-pantry.html").write_text("<html><body>Riverbend</body></html>", encoding="utf-8")
    (tmp_path / "secret.html").write_text("SECRET", encoding="utf-8")
    monkeypatch.setattr(web, "DEMO_PAGES_DIR", pages)
    return pages


async def test_fetch_local_demo_page(demo_dir):
    for url in ("http://127.0.0.1:8000/demo/riverbend-pantry.html", "http://localhost:5173/demo/riverbend-pantry.html"):
        page = await web.fetch_url(url)
        assert page.error is None and page.status == 200
        assert "Riverbend" in page.html and page.content_type.startswith("text/html")
    missing = await web.fetch_url("http://127.0.0.1:8000/demo/nope.html")
    assert missing.status == 404 and missing.error


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/demo/../secret.html",
        "http://127.0.0.1:8000/demo/..%2Fsecret.html",
        "http://127.0.0.1:8000/demo/sub/secret.html",
        "http://127.0.0.1:8000/demo/.hidden.html",
        "http://127.0.0.1:8000/demo/riverbend-pantry.txt",
        "http://127.0.0.1:8000/api/health",
    ],
)
async def test_fetch_rejects_traversal_and_non_demo_local(demo_dir, url):
    page = await web.fetch_url(url)
    assert page.error and page.html == ""


async def test_fetch_offline_and_bad_scheme_never_raise():
    page = await web.fetch_url("https://www.example.org/")
    assert page.error and "OFFLINE_MODE" in page.error
    for url in ("file:///etc/passwd", "ftp://example.org/x", "", "not a url"):
        page = await web.fetch_url(url)
        assert page.error and page.html == ""


async def test_fetch_blocks_private_ip_even_online(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "0")
    page = await web.fetch_url("http://169.254.169.254/latest/meta-data/")
    assert page.error and "private" in page.error


async def test_web_search_returns_empty_when_ddgs_raises(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "0")

    def boom(query, max_results):
        raise RuntimeError("ratelimited")

    monkeypatch.setattr(web, "_ddgs_text", boom)
    assert await web.web_search("Connecticut Foodshare") == []


async def test_web_search_maps_and_clips(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "0")

    def fake(query, max_results):
        return [
            {"title": "CT Foodshare", "href": "https://www.ctfoodshare.org/", "body": "x" * 2000},
            {"title": "bad", "href": "javascript:alert(1)", "body": "no"},
        ]

    monkeypatch.setattr(web, "_ddgs_text", fake)
    results = await web.web_search("Connecticut Foodshare", max_results=3)
    assert [r.url for r in results] == ["https://www.ctfoodshare.org/"]
    assert len(results[0].snippet) <= web.SNIPPET_MAX_CHARS


async def test_web_search_offline_returns_empty(monkeypatch):
    called = []
    monkeypatch.setattr(web, "_ddgs_text", lambda q, n: called.append(q) or [])
    assert await web.web_search("anything") == []
    assert called == []


def test_cost_discipline_drops_unused_growth_driver():
    profile = _profile([_filing(2024)])
    card = score_charity(profile, _metrics(**dict(STRONG, expense_cagr_3y=None)), _impact(3), Weights())
    cost = next(d for d in card.dimensions if d.dimension == "cost_discipline")
    assert "CALC-123456789-revenue_cagr_3y" not in cost.drivers
    assert "expense_cagr_3y" in cost.missing_inputs
    assert "expense growth versus revenue growth could not be computed" in cost.explanation


async def test_web_search_retries_once_with_a_shorter_query(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "0")
    seen = []

    def fake(query, max_results):
        seen.append(query)
        return [] if len(seen) == 1 else [{"title": "IRIS", "href": "https://irisct.org/", "body": "Refugee services"}]

    monkeypatch.setattr(web, "_ddgs_text", fake)
    results = await web.web_search("Integrated Refugee & Immigrant Services IRIS Connecticut impact outcomes evaluation")
    assert [r.url for r in results] == ["https://irisct.org/"]
    assert seen[1] == "Integrated Refugee Immigrant Services IRIS Connecticut"


def test_unreadable_website_leaves_impact_unscored_not_zero():
    profile = load_cached_profile("061063025")
    metrics, _ = financials.compute_metrics(profile, today=date(2026, 10, 26))
    blocked = ImpactAssessment(ein=profile.ein, evidence_level=0, pages_read=[], evidence_ids=[])
    card = score_charity(profile, metrics, blocked, Weights())
    impact = next(d for d in card.dimensions if d.dimension == "impact_evidence")
    assert impact.score is None
    assert "could not be read" in impact.explanation
    assert card.overall is not None and card.band != "insufficient_data"
