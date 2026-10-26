# Scoring rubric (hypothesis-based)

This rubric is a **hypothesis**, not an industry standard and not a finding. It turns the
deterministic metrics from `backend/app/tools/financials.py` into five 0–100 dimension scores so a
donor can compare charities on one scale. The thresholds below are our judgement. Where Charity
Navigator publishes a comparable threshold we copy or adapt it and say so; every other threshold is
labelled "our hypothesis". The code that applies it is `backend/app/tools/scoring.py` (`RUBRIC`);
the two must stay in sync.

Data source for every input: IRS Form 990 data from the ProPublica Nonprofit Explorer API
(<https://projects.propublica.org/nonprofits/api>), plus the impact researcher's reading of the
charity's own website for the impact and website-disclosure inputs.

## 1. How a score is built

1. **Sub-score per input.** Each input gets a piecewise-linear score between the breakpoints in the
   tables below. Between two breakpoints the score is a straight line; beyond the first or last
   breakpoint it stays flat at that breakpoint's score. Charity Navigator uses the same linear
   scaling between an upper and a lower threshold.
2. **Dimension score.** The mean of the sub-scores that could be computed, rounded to 0.1. If none
   of a dimension's inputs exist, the dimension is `null` (not 0).
3. **Missing inputs.** A metric that is `null` (missing field, zero denominator, too few filings) is
   left out of the mean and listed in `missing_inputs`. It is never treated as 0.
4. **Overall.** The weighted mean of the non-null dimensions, using the donor's weights (0 to 5).
   If every weight is 0, all weights are treated as 1.
5. **Band.**

| Condition | Band |
|---|---|
| Two or more dimensions are `null`, or the charity has no filings with data, or no overall can be computed | `insufficient_data` |
| Overall ≥ 70 | `strong_fit` |
| 50 ≤ overall < 70 | `fit_with_questions` |
| Overall < 50 | `weak_fit` |

The band cut-offs (70 and 50) are our hypothesis.

## 2. Thresholds

"Score" columns give the sub-score at each breakpoint. Ratios are written as percentages.

### Financial health

Sub-scores: operating results (mean of the two margin scores that exist), reserves, leverage.

| Input (metric key) | Breakpoints (value → score) | Anchor |
|---|---|---|
| Surplus margin, latest year (`surplus_margin`) | ≤ −10% → 0; 0% → 50; ≥ 5% → 100 | Our hypothesis. Charity Navigator does not score operating margin. |
| Average surplus margin, up to 3 years (`avg_surplus_margin_3y`) | ≤ −10% → 0; 0% → 50; ≥ 5% → 100 | Our hypothesis. Averaging over 3 years follows Charity Navigator's practice of using three recent fiscal years for several metrics. |
| Reserves proxy, net assets in months of expenses (`net_assets_months`) | ≤ 1 month → 0; ≥ 6 months → 100 | Adapted from Charity Navigator's Working Capital Ratio ("all other cases": no credit below 0.08333 of a year, that is 1 month; full credit at 0.5 of a year, that is 6 months). Our input is weaker: net assets include buildings and restricted funds, so this overstates liquid reserves. Large reserves are not penalised. |
| Liabilities to assets (`liabilities_to_assets`) | ≤ 30% → 100; ≥ 70% → 0 | Copied from Charity Navigator's Liabilities to Assets Ratio for medium to super-sized donor-funded charities (0.3 = full credit, 0.7 = no credit). Charity Navigator uses 0.5 = full credit for "all other cases"; we apply the stricter donor-funded scale to everyone. |

### Revenue resilience

| Input | Breakpoints | Anchor |
|---|---|---|
| Revenue concentration index (`revenue_concentration_hhi`), sum of squared shares of contributions, program service revenue, investment income and other revenue | ≤ 0.40 → 100; 1.00 (single source) → 50 | Our hypothesis. Not an industry standard. The four categories cannot see donor-level concentration: one large grant and 10,000 small gifts both count as "contributions", so a single-source charity keeps a floor of 50. |
| Revenue volatility, coefficient of variation over up to 5 years (`revenue_volatility_cv`) | ≤ 5% → 100; 15% → 70; ≥ 40% → 0 | Our hypothesis. Steady growth also raises this number, so it overstates risk for fast-growing charities. |
| Revenue growth per year, about 3 years (`revenue_cagr_3y`) | ≤ −10% → 0; 0% → 60; ≥ 5% → 100 | Our hypothesis. Charity Navigator's current Encompass finance metrics do not score revenue growth. |

### Cost discipline

| Input | Breakpoints | Anchor |
|---|---|---|
| Officer compensation as a share of expenses (`officer_comp_share`) | ≤ 5% → 100; 15% → 60; ≥ 30% → 0 | Our hypothesis. Charity Navigator checks that CEO pay is disclosed and that a pay-setting policy exists, but does not score pay as a share of expenses. Small charities with one paid director score lower on this input by construction. |
| Professional fundraising fees as a share of contributions (`pro_fundraising_fee_share`) | ≤ 2% → 100; 10% → 50; ≥ 20% → 0 | Adapted from Charity Navigator's Fundraising Efficiency (all fundraising expenses per dollar of contributions; full credit at 0.20 or less, no credit above 0.50). Our input is only outside fundraisers' fees (Form 990 Part IX line 11e), a subset of fundraising cost, so our scale is stricter. Total fundraising expense is not in the free extract. |
| Expense growth minus revenue growth, per year (`expense_cagr_3y` − `revenue_cagr_3y`) | ≤ 0 points → 100; 5 points → 50; ≥ 10 points → 0 | Our hypothesis. Expenses growing faster than revenue for three years is a question to ask, not proof of a problem. |

### Transparency

| Input | Breakpoints | Anchor |
|---|---|---|
| Years since the latest filing with data (`filing_recency_years`) | ≤ 3 years → 100; 4 → 50; ≥ 5 → 0 | Adapted. The ProPublica extract normally lags 2 to 3 years behind the calendar year, so 3 years is treated as current. Charity Navigator drops data from its rating after four years. |
| Years of filings with data (`years_of_filings`) | 0 → 0; 1 → 20; 3 → 70; ≥ 5 → 100 | Our hypothesis. |
| Website publishes financial reports (`publishes_financials`, from the impact review) | yes → 100; no → 0; unknown → left out | Our hypothesis, informed by Charity Navigator's Website Disclosures check. |
| Website publishes outcome data (`publishes_outcomes`, from the impact review) | yes → 100; no → 0; unknown → left out | Our hypothesis. |

### Impact evidence

| Evidence level (from the impact review) | Score |
|---|---|
| 0: No information found about results | 0 |
| 1: Stories or anecdotes only | 25 |
| 2: Reports outputs (people served, meals, etc.) | 50 |
| 3: Reports measured outcomes against goals | 75 |
| 4: Independent evaluation or rigorous study | 100 |

No impact review (agent error, no website) makes this dimension `null`. The level scale is our
hypothesis. Charity Navigator's Impact & Measurement beacon uses data that charities submit through
its portal, which we do not have.

## 3. What is shown but not scored

| Metric | Why it is not scored |
|---|---|
| Program expense share (`program_expense_share`) | Always `null`: "Not in the free IRS extract (Form 990 Part IX, column B). Ask the charity or read the filing PDF." Charity Navigator scores this ratio (full credit at 85% for medium to super donor-funded charities, 70% for small ones, no credit at 50%); we show those numbers as context only and turn the gap into a question for the charity. If the charity's own site reports it, the memo labels it "self-reported, unverified". |
| Contributions share of revenue (`contributions_share`) | Context for the concentration index. |
| Staff cost share (`staff_cost_share`) | Context. Staff-heavy programs (tutoring, case management) are not worse by default. |
| Total revenue and total expenses, latest year | Size context. |

## 4. Known limits

- Thresholds are the same for every cause area and size, except where noted. Charity Navigator
  varies several thresholds by size (micro under $500K to super over $50M) and by type (non-cash,
  grant-making, museums); we do not.
- Form 990-EZ and 990-PF filings have fewer fields, so their cost-discipline score rests on fewer
  inputs. Private foundations (990-PF) are not the intended use.
- The rubric weighs financial filings heavily because they are the only data verified by a third
  party (the IRS). It does not measure whether a program works; the impact evidence dimension only
  records how much evidence the charity publishes.

## 5. Sources checked (2026-10-26)

- Charity Navigator, "Accountability & Finance" methodology page:
  <https://www.charitynavigator.org/about-us/our-methodology/ratings/accountability-finance/>
  (lists the finance metrics: program expense ratio, liabilities to assets, working capital,
  fundraising efficiency; eligibility by revenue size).
- Charity Navigator, Rating Methodology Guide (linked from the page above):
  <https://docs.google.com/document/d/1uIE5inGipHtqjhH1hM-8MiIBHqMXD5nSwA9F2bcXmT4/edit?tab=t.0>
  (threshold tables quoted above: liabilities to assets 0.3 / 0.7 for donor-funded charities and
  0.5 / 0.7 for all other cases; working capital 0.5 / 0.08333 of a year; fundraising efficiency
  0.2 / 0.5; program expense ratio 0.85 / 0.5 and 0.7 / 0.5; linear scaling between thresholds;
  data removed after four years; size classes).
- Charity Navigator, guide to the Spring 2026 methodology:
  <https://www.charitynavigator.org/about-us/news-thought-leadership/our-enhanced-encompass-rating-system/>
  (adds self-submitted Impact Reporting, Workplace Policies and Board-Approved Budget metrics; only
  full Form 990 filers get an overall score; no change to the finance thresholds is described).
- ProPublica Nonprofit Explorer API: <https://projects.propublica.org/nonprofits/api>
