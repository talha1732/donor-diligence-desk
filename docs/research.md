# Research: market, donor behaviour, competitors, and impact estimates

Owner: Research builder. All sources accessed **2026-10-26** unless stated. "Press release" or
"secondary" marks numbers we could not check against the primary document. Numbers we derived
ourselves are labelled "our calculation" or "our estimate".

## Key numbers for the report

| # | Fact | Source |
|---|---|---|
| 1 | US charitable giving reached **$617.2 billion in 2025**; individuals gave **$394.2 billion (about 64%)**. | Giving USA 2026 via IU Lilly Family School of Philanthropy, https://philanthropy.indianapolis.iu.edu/professional-development/blog/the-giving-usa-2026-report-deserves-a-closer-look.html |
| 2 | The IRS recognised **1,596,231 section 501(c)(3) organizations** in FY2025 (includes private foundations). | IRS Data Book FY2025, Table 2-6, https://www.irs.gov/pub/irs-soi/25db-2-06-eo.xlsx |
| 3 | Charity Navigator rates **more than 245,000** charities (about 15% of 501(c)(3)s, our calculation). Its Impact & Results beacon covered only **2,506** charities at end of 2023. CharityWatch rates about **600**; GiveWell recommends **4** top charities. | https://www.charitynavigator.org/about-us/ ; https://www.charitynavigator.org/about-us/news-thought-leadership/2023-reflections/ ; https://en.wikipedia.org/wiki/CharityWatch ; https://www.givewell.org/charities/top-charities |
| 4 | Only **35%** of donors researched before giving and **2%** gave based on a charity's relative performance, although **85%** said performance is very important (Money for Good, 2010, poll of 4,000). | Chronicle of Philanthropy, 2010-06-02, https://www.philanthropy.com/news/donors-value-charity-research-but-few-seek-it-out-report-finds/ |
| 5 | **67.7%** of Americans say trusting a charity is essential before giving, but only **18.3%** report high trust. Among those who seek information, **54%** are influenced by charity websites, **39%** by third-party monitors, **7%** by AI summaries. | BBB Wise Giving Alliance, Donor Trust Report 2026 (survey of 1,500+ adults, Dec 2025), https://give.org/donor-trust-report/2026-trends-in-donor-trust-and-perspectives |
| 6 | **December is about 18%** of annual giving and **Q4 is more than 36%** (7,500+ nonprofits, $66B+ revenue). | Blackbaud Institute, 2025 trends release, 2026-03-18, https://www.blackbaud.com/?p=45112 |
| 7 | GivingTuesday 2025 (Dec 2) raised **$4.0 billion in the US**; **19.1 million** people made financial gifts. | https://www.givingtuesday.org/blog/2025-results |
| 8 | Donor-advised funds granted **$64.60 billion** in FY2024 from 3.59 million accounts. Fidelity Charitable alone granted **$18.3 billion** in 2025 to **226,823** charities. | DAF Research Collaborative (spring 2026 revision), https://www.dafresearchcollaborative.org/research/annual-daf-report ; https://www.fidelitycharitable.org/insights/2026-giving-report.html |
| 9 | About **4,000 giving circles** with **370,000 members** gave **$3.1 billion** in the seven years to 2023 (secondary summary of the 2024 "In Abundance" report). | Foundation Source, 2024-05-08, https://foundationsource.com/blog/collective-giving-is-on-the-rise-and-shifting-the-philanthropy-landscape/ |
| 10 | Eight AI search tools gave **incorrect answers to more than 60%** of 1,600 citation queries (range 37% Perplexity to 94% Grok 3). | Tow Center / CJR, 2025-03-06, https://www.cjr.org/tow_center/we-compared-eight-ai-search-engines-theyre-all-bad-at-citing-news.php |
| 11 | Program-expense share needs Form 990 Part IX column B, which is **not in ProPublica's free extract** ("only a subset of what can be found in the full Form 990s"). The extract also lags: MSF USA FY2024 shows on ProPublica's web page but the API's newest filing with data is FY2023. | https://projects.propublica.org/nonprofits/ ; https://projects.propublica.org/nonprofits/organizations/133433452 ; live API check 2026-10-26 |
| 12 | Our estimate: reading 3 years of 990s for 3 charities by hand takes **3 to 6 hours**; at the **$36.14/hour** value of volunteer time that is **$108 to $217** of donor time, against a per-run model budget cap of **$0.10**. | Our estimate (section 7); Independent Sector, 2026-04-21, https://independentsector.org/research/value-of-volunteer-time/ ; `docs/contract.md` |

---

## 1. Who has the problem

| Measure | Value | Source and notes |
|---|---|---|
| Total US giving, 2025 | $617.20B, up 5.7% current dollars, 3.0% after inflation | Giving USA 2026, https://philanthropy.indianapolis.iu.edu/professional-development/blog/the-giving-usa-2026-report-deserves-a-closer-look.html |
| Giving by individuals, 2025 | $394.2B (63.9% of total, our calculation; Ohio CPA summary says 64%, down from 67% in 2023 and 66% in 2024) | Same; https://ohiocpa.com/for-the-public/news/2026/07/10/key-takeaways-from-giving-usa-on-2025-philanthropy-trends |
| Foundations / bequests / corporations, 2025 | $117.15B / $62.19B / $43.67B | Giving USA 2026 (IU Lilly page above) |
| 501(c)(3) organizations, FY2025 | 1,596,231 (all exempt orgs: 2,068,741) | IRS Data Book Table 2-6, https://www.irs.gov/pub/irs-soi/25db-2-06-eo.xlsx (footnote: includes private foundations and group-exemption members) |
| Family foundations | 38,701 independent foundations with measurable donor or donor-family involvement, "more than half of all independent foundations" (2009 data) | Foundation Center, Key Facts on Family Foundations, 2011-01-21, https://candid.issuelab.org/resource/key-facts-on-family-foundations-2011 . Dated; we found no newer official count. NCFP's Trends 2025 survey gives no total (https://www.ncfp.org/resource/trends-research). |
| Giving circles | ~4,000 groups, ~370,000 members, $3.1B over 2017–2023; groups and members tripled 2016–2023; most members give under $1,000 a year | "In Abundance" (Johnson Center, Colmena, Philanthropy Together, April 2024), report page https://johnsoncenter.org/resource/report-in-abundance-an-analysis-of-the-thriving-landscape-of-collective-giving-in-the-u-s/ . Figures from secondary summaries (Foundation Source, Inside Philanthropy, Axios); we could not extract the PDF text. |
| DAF grants, FY2024 | $64.60B grants, $90.57B contributions, $327.87B assets, 3.59M accounts, 25.2% payout | DAF Research Collaborative, spring 2026 revised analysis, https://www.dafresearchcollaborative.org/research/annual-daf-report (from the 2025 edition the annual DAF report is produced by the DAFRC instead of National Philanthropic Trust: https://johnsoncenter.org/resource/report-annual-daf-report-2025/) |
| Largest DAF sponsors | Fidelity Charitable: $18.3B granted in 2025, 395,515 donors, 3M grants, 226,823 charities. DAFgiving360 (formerly Schwab Charitable): "nearly $10 billion" in calendar 2025 (press release) | https://www.fidelitycharitable.org/insights/2026-giving-report.html ; https://www.businesswire.com/news/home/20260127969044/en/ |
| Year-end concentration | December ~18% of annual giving; Q4 >36% | Blackbaud Institute, 2026-03-18, https://www.blackbaud.com/?p=45112 |
| GivingTuesday 2025 | $4.0B US (+13%), 38.1M participants, 19.1M financial contributors | https://www.givingtuesday.org/blog/2025-results . GivingTuesday 2026 is Dec 1. |

**The person behind the problem.** The users are an individual or a household giving a few
thousand dollars at year end, a giving-circle member (most give under $1,000 a year and the giving is mostly
local), or a trustee of a small family foundation with no staff. All three make decisions in a
short December window, and none has a program officer to read filings.

## 2. How donors decide today

| Finding | Number | Source |
|---|---|---|
| Donors who research before giving (Money for Good, 2010; poll of 4,000, incomes over $80K) | 35% research; 2% give based on relative performance; 85% say performance is very important | Chronicle, 2010-06-02, https://www.philanthropy.com/news/donors-value-charity-research-but-few-seek-it-out-report-finds/ |
| Same study, restated by its authors | "only 3 out of 10 donors actually research nonprofits," while 9 in 10 say they care about performance; 53% want to use third-party rating portals but few know they exist | Ottenhoff and Ulrich, SSIR, 2012-03-19, https://ssir.org/articles/entry/three_steps_to_more_informed_giving |
| Money for Good II (2011; 5,000+ donors, 800+ advisors, 700+ foundations) | About 20% of donors regularly research; impact information was donors' "biggest under-met need"; up to $15B (about 5% of giving) could shift to higher performers | Bridgespan guest post by Greg Ulrich, 2011-12-15, https://www.bridgespan.org/insights/donors-want-more-information-on-impact ; SSIR 2012 (above) |
| Why donors skip research | Loyalty to charities they already support; new charities "already seem well-known and vetted" | SSIR 2012 (above) |
| Trust gap (Dec 2025 survey, 1,500+ adults) | 67.7% say trust is essential; 18.3% report high trust; gap stable since 2017 | Give.org Donor Trust Report 2026, https://give.org/donor-trust-report/2026-trends-in-donor-trust-and-perspectives |
| What influences information seekers | Charity websites 54%; third-party monitors 39%; AI summaries 7% | Same |
| AI as a discovery channel | "nearly six million donors now cite AI as a preferred tool for finding and learning about causes" (GWI survey, cited secondhand); organic search traffic to nonprofit sites down 35% in a year while AI referrals rose 1,000%+ (Blue State, Nov 2025) | Candid blog, 2026-09-23, https://candid.org/blogs/ai-and-fundraising-donors-search/ (secondary figures) |
| Charity Navigator usage | Traffic fell in 2023 "for the first time in 10 years"; Giving Basket moved $41.6M to 25,000+ charities in 2023 | https://www.charitynavigator.org/about-us/news-thought-leadership/2023-reflections/ (no current visitor count published) |

**Reading.** Donors say performance matters but few check it. The ones who do check rely first on the
charity's own website, which is the least independent source. AI is starting to be used for
discovery (7% today per Give.org), and current AI search tools get citations wrong often (section 4).
The 2010 and 2011 studies are old, and we did not find a newer survey with the same questions.

## 3. Time and cost of doing diligence by hand

**What the documents look like.**
- The Form 990 itself is **12 pages** (current IRS revision, https://www.irs.gov/pub/irs-pdf/f990.pdf ,
  page count checked) and its instructions run to about **100 pages**
  (https://www.irs.gov/pub/irs-pdf/i990.pdf). Filings add Schedules A to R and attachments.
- The numbers a donor needs are spread across Part I (summary), Part VII (compensation), Part VIII
  (revenue), Part IX (functional expenses: column B program, C management and general, D
  fundraising) and Part X (balance sheet). Comparing three years means doing this three times per charity.
- **Program-expense share is not in the free data.** ProPublica says its data release "includes only a
  subset of what can be found in the full Form 990s" (https://projects.propublica.org/nonprofits/).
  Our cached API responses have 68 fields per filing and none for the Part IX functional columns
  (checked in `backend/data/cache/propublica/org_061063025.json`). Charity Navigator's program
  expense ratio uses Part IX line 25B / 25A and its fundraising efficiency uses line 25D (see section 6),
  so neither can be computed from the free extract.
- **The free extract lags the filings.** In our cache, 7 of the 7 test charities have a newer filing
  listed as "without data" (PDF only) than the newest filing with data (for example Connecticut
  Foodshare FY2025, Columbus House FY2024 and FY2025). ProPublica's web page for MSF USA shows FY2024
  figures while the live API (checked 2026-10-26) still returns FY2023 as the newest filing with data.
- **Audited statements and the 990 extract differ a little.** Our ground-truth check
  (`evals/ground-truth.csv`) compared audited statements with the extract for 6 charities. Total
  assets match for all 6 (largest gap $843 at IRIS); liabilities and net assets match within 0.25%
  (Columbus House's audit consolidates subsidiaries). Revenue and expenses differ by 0.01%
  (Habitat GNH) up to 4.8% and 4.9% (Feeding America, GAAP versus 990 presentation). A donor
  reading two sources sees two different "revenue" numbers.

**Published time estimates (few exist).**
| Estimate | Value | Source and caveat |
|---|---|---|
| Manual due diligence at a $900M foundation before automation | 4 hours per organization; 200 hours for 50 organizations | Impala blog, 2026-03-18, https://impala.digital/blog/how-a-major-foundation-cut-due-diligence-from-hours-to-clicks . Vendor marketing; foundation not named. |
| GiveWell research effort | "70,000+ hours of research annually" behind 4 top charities | https://www.givewell.org/charities/top-charities . Shows the cost of deep impact diligence, not a donor task. |
| Nonprofit Overhead Cost Study (220,000+ Form 990s) | More than a third of organizations reported no fundraising costs; 1 in 8 reported no management and general expenses | Gregory and Howard, SSIR, Fall 2009, https://ssir.org/articles/entry/the_nonprofit_starvation_cycle . Reported functional splits are unreliable. |

We found no peer-reviewed estimate of donor time per charity, so section 7 builds a labelled estimate.

## 4. Existing products: honest comparison

| Product | What it does | Coverage | Cost to donor | Where it is better than this app | Gap this app fills |
|---|---|---|---|---|---|
| **Charity Navigator** (Encompass) | 0–4 star rating from weighted metrics in four beacons; Accountability & Finance uses 990 ratios (section 6); Horizon AI Search (Nov 2025) for natural-language discovery; data feeds Perplexity (Dec 2024) | 245,000+ rated (https://www.charitynavigator.org/about-us/); needs 3 e-filed full Form 990s, so 990-EZ and 990-N filers are unrated (methodology guide, section 6); Impact & Results beacon on 2,506 charities at end of 2023 | Free | Much larger coverage; analyst review; uses the full 990 including Part IX; established brand; charity self-reported data via portal | One score for everyone, not weighted to the donor's priorities; no per-number source trail; no questions to ask; small local charities filing 990-EZ or 990-N have no rating |
| **CharityWatch** | Analyst-adjusted A+ to F grades from Program % and Cost to Raise $100, using audited statements | About 600 large national charities (https://en.wikipedia.org/wiki/CharityWatch) | Most content free; full profiles $50/year (Wikipedia, not checked on charitywatch.org, which returned 403) | Deeper manual adjustment of audited financials than any automated tool | Very small coverage; no local charities; grades centre on overhead ratios |
| **Candid** (GuideStar profiles, Seals of Transparency) | Profiles with 990 financials, mission, programs; Seals reward disclosure, not performance; AI assistant answering social-sector questions from Candid resources (2025-01-13, https://candid.org/blogs/introducing-candids-ai-assistant-chatgpt-for-nonprofits/) and a Claude connector for nonprofits (2025-12-02) | 1.9 million organizations (https://candid.org/press/candid-partners-with-anthropic-to-bring-trusted-data-to-claude-for-nonprofits/) | Free basic profiles; Premium $219/month or $1,199/year; Ultimate $1,699/year (https://candid.org/pricing/) | Broadest coverage; financial data "more recent than the IRS" for paid users; self-reported program and outcome data | Not a judgment or a memo; paid tiers priced for fundraisers; the Claude connector targets fundraisers and nonprofits, not donors (per the Dec 2025 release); the assistant answers sector questions rather than assessing a named charity's filings |
| **GiveWell** | Deep cost-effectiveness research; top charities and funds | 4 top charities, global health (https://www.givewell.org/charities/top-charities); raised $616M in its 2025 metrics year (https://files.givewell.org//files/metrics/GiveWell_Metrics_Report_2025.pdf, secondary summary) | Free | Far stronger impact evidence than anything automated can produce | Does not cover US local charities or a donor's own shortlist |
| **Giving What We Can** | Evaluates evaluators; recommends funds and charities that vetted evaluators recommend | A short list of funds and charities across global health, animal welfare, catastrophic risk (https://www.givingwhatwecan.org/2025-evaluator-research) | Free | Rigorous for its cause areas | Same as GiveWell: not built for "is this local charity sound?" |
| **ProPublica Nonprofit Explorer** | Free search and API over IRS 990 extracts, PDFs, single audits | Millions of returns since 2012 (https://projects.propublica.org/nonprofits/) | Free | Primary data; full PDFs; journalist-grade neutrality | No ratios, no scoring, no interpretation; extract omits Part IX functional columns and lags the PDFs (section 3) |
| **BBB Wise Giving Alliance** (Give.org) | Pass/fail against 20 BBB Standards (governance, results reporting, finances, solicitations); program spend at least 65% of expenses, fundraising at most 35% of related contributions | "Thousands of charity reports" (https://give.org/news/inside-our-charity-evaluation-process); national charities; local BBBs cover more | Free (evaluations are free to charities too) | Checks solicitation truthfulness and governance with the charity's cooperation | Voluntary participation; pass/fail, no donor weighting; slow manual process |
| **DAF sponsor tools** (Fidelity Charitable, DAFgiving360) | Link out to GuideStar, Charity Navigator, Giving Compass; Fidelity says it "does not endorse" them | Whatever the linked tool covers | Free to account holders | Sit where large year-end gifts are made | No in-account diligence; the donor still assembles the picture (https://www.fidelitycharitable.org/guidance/research-charities.html) |
| **AI features in charity tools, 2024–2026** | Charity Navigator Horizon AI Search (natural-language discovery, Nov 2025, https://www.einpresswire.com/article/869704126/); Perplexity answers using Charity Navigator data (Dec 2024, https://www.perplexity.ai/hub/blog/research-nonprofits-with-charity-navigator-on-perplexity); Candid Claude connector (Dec 2025); ClearGiving (configurable scoring and audit trail for funders and individual philanthropists, data sources and launch date not stated, https://cleargiving.io/who-its-for) | Varies | Free to paid | Large data assets behind them | Mostly discovery, not diligence; we found no donor-facing tool that computes ratios from filings, traces every number, weights to donor priorities, and writes questions for the charity |
| **General chatbots** (ChatGPT, Perplexity, Gemini, incl. deep research modes) | Open-ended web research and summaries | Anything on the web | Free tiers to monthly subscriptions | Flexible; can read annual reports and news; fast | Numbers can be invented or mis-cited: 60%+ incorrect citation answers across 8 tools (https://www.cjr.org/tow_center/we-compared-eight-ai-search-engines-theyre-all-bad-at-citing-news.php); OpenAI said deep research can "sometimes hallucinate facts in responses or make incorrect inferences" (as quoted by Verdict, 2025-02-03, https://www.verdict.co.uk/openai-launches-ai-research-agent/); no fixed rubric, so results vary run to run; web pages can carry prompt injections |

**What is different about this app.** It uses the same free IRS data as ProPublica, but (1) every
number on screen links to an evidence entry (API field, deterministic calculation, or quoted web
excerpt), and numbers that fail verification are removed, (2) the score is weighted to the donor's stated priorities,
(3) metrics that cannot be computed (program share) become questions to ask instead of guesses,
(4) it works for any charity that files a full Form 990 with ProPublica data, including local ones
outside GiveWell or CharityWatch coverage, and (5) web content is sanitized before any model reads it.
**Where it is weaker:** no analyst review, no use of Part IX or audited statements, impact
evidence is limited to what the charity publishes, and the ProPublica extract can be a year or more behind.

## 5. Overhead-ratio critiques and why the app does not guess program share

- **"The Overhead Myth" (June 2013).** The CEOs of GuideStar, Charity Navigator, and the BBB Wise
  Giving Alliance wrote to donors that the share of expenses going to administration and fundraising
  "is a poor measure of a charity's performance" and asked donors to weigh "transparency, governance,
  leadership, and results." Chronicle, 2013-06-17,
  https://www.philanthropy.com/news/3-major-charity-groups-ask-donors-to-stop-focusing-on-overhead-costs/ ;
  https://www.charities.org/news/help-end-overhead-myth (the original overheadmyth.com no longer resolves).
- **The Nonprofit Starvation Cycle (SSIR, 2009).** Funders' unrealistic overhead expectations push
  nonprofits to underspend on infrastructure and underreport costs. More than a third of organizations
  reported zero fundraising costs, so reported ratios are unreliable. https://ssir.org/articles/entry/the_nonprofit_starvation_cycle
- **The raters still use the ratio.** Charity Navigator's 2026 methodology still scores the program
  expense ratio (section 6), BBB keeps its 65% standard, and CharityWatch grades on Program %.

**App policy.** Program-expense share is `null` with the reason "Not in the free IRS extract (Form
990 Part IX, column B)" and becomes a question for the charity. If the charity's own site states it,
the memo labels it "self-reported, unverified". Reasons: the field is absent from the data
(section 3); filling it with an estimate would break the "numbers only from tools" rule; and the
overhead critique argues against weighting it heavily anyway. The app scores reserves, leverage,
revenue mix and stability, growth, and officer pay, which the extract does contain.

## 6. Charity Navigator Encompass thresholds (anchor for `docs/scoring-rubric.md`)

Source: Charity Navigator Rating Methodology Guide (Spring 2026 methodology; "updated on a rolling
basis"; search index titles it "Last updated: March 2026"), linked from
https://www.charitynavigator.org/about-us/our-methodology/ratings/ as
https://docs.google.com/document/d/1uIE5inGipHtqjhH1hM-8MiIBHqMXD5nSwA9F2bcXmT4/edit . Text exported
and read 2026-10-26.

**Scoring mechanics.** Each metric is scored 0 to 1 and scaled linearly between a lower and upper
threshold. The star rating is a weighted average of eligible metrics. Ineligible metrics are dropped rather than scored zero.
Star bands (ratings page): 4 stars 90+, 3 stars 75–89, 2 stars 60–74, 1 star 50–59, 0 stars below 50.

**Size classes (total revenue):** Super > $50M; Large $25M–$50M; Medium $2M–$25M; Small > $500K to
$2M; Micro < $500K. "Donor funded" means public donations, fundraising, and dues exceed 40% of revenue.

**Rating eligibility:** US 501(c)(3) public charity; at least three e-filed Form 990s in the past six
years; at least two of the four most recent are the full Form 990, and the most recent is not a
990-EZ, 990-N, or 990-PF.

| Metric | Formula (Form 990) | Eligibility | Full credit (1) | No credit (0) |
|---|---|---|---|---|
| Program expense ratio | 3-yr average Part IX 25B / 25A | All sizes | Medium–Super, donor funded or non-cash: **≥ 0.85**. Small, Micro, other: **≥ 0.70**. Museums: **≥ 0.65** | **≤ 0.50** in all cases |
| Liabilities to assets | Part X line 26 / line 16, latest year | All sizes | Medium–Super donor funded, non-cash, museums: **≤ 0.30**. Grant-making: **≤ 0.35**. Grants payable: **≤ 0.50**. All other cases: **≤ 0.50** | **≥ 0.70** (grant-making 0.80; grants payable 0.90; other 0.70). Assets = 0 gets no credit |
| Working capital ratio | (Part X line 27 + line 28) / average Part IX 25A, in years | Donor funded, revenue > $2M | **≥ 0.5 years (6 months)**; museums 1.5 years; non-cash 0.25 years | **< 0.08333 years (1 month)** |
| Fundraising efficiency | 3-yr average Part IX 25D / 3-yr average Part VIII 1h | Donor funded, revenue > $2M | **≤ $0.20** per $1 raised (non-cash ≤ $0.05) | **> $0.50** (non-cash > $0.25) |

Worked example from the guide: program ratio 0.76 with thresholds 0.85 / 0.5 scores (0.76 − 0.5) /
(0.85 − 0.5) = 0.74.

**Mapping to this app.** Part X lines 27 and 28 are net assets without and with donor restrictions,
so Charity Navigator's working capital ratio is close to the app's `net_assets_months` / 12. The difference is
that Charity Navigator divides by average expenses and the app divides by latest-year expenses.
`liabilities_to_assets` maps directly. Program expense ratio and fundraising efficiency need Part IX
columns B and D, which the free extract lacks, so the app does not score them. It uses
`pro_fundraising_fee_share` (Part IX line 11e professional fundraising fees / contributions) as a
partial substitute and says so. Other raters' thresholds for comparison: BBB Standard 8, program ≥ 65% of total expenses; Standard 9, fundraising ≤ 35% of related
contributions (https://give.org/bbb-standards-for-charity-accountability). CharityWatch's top-rated list generally
requires ≥ 75% program and ≤ $25 to raise $100 (CharityWatch top-rated page via search; site
returned 403 to our fetch).

## 7. Impact framing: time saved and value at scale (our estimate, assumptions labelled)

**Manual baseline, one charity, three years of filings (assumptions, not measured):**

| Step | Minutes | Basis |
|---|---|---|
| Find the charity and open three 990 PDFs on ProPublica | 5 | Assumption |
| Read Parts I, VII, VIII, IX, X for each year (12-page core form plus schedules) | 15 per year, 45 total | Assumption; Form 990 structure from IRS |
| Enter figures in a spreadsheet and compute about 10 ratios | 15 | Assumption |
| Read the website or annual report for outcome evidence | 15 | Assumption |
| Write notes and questions for the charity | 10 | Assumption |
| **Total per charity** | **90 (range 60–120)** | Consistent with the one-to-two-hour figure in AGENTS.md; below the 4-hour foundation anecdote (Impala) |

**Per decision (three charities):** 3 to 6 hours by hand (midpoint 4.5 hours). App: one run of
about 2 minutes (target; measure with `evals/`) plus about 10 minutes to read the memo. Time saved:
about 4 hours per decision.

**Value of time.** Independent Sector values a volunteer hour at **$36.14** for 2025 (preliminary;
released 2026-04-21, https://independentsector.org/research/value-of-volunteer-time/). Manual
diligence for three charities is therefore worth **$108 to $217** of donor time (midpoint **$163**).
The app's per-run budget cap is **$0.10** (`RUN_BUDGET_USD` in `docs/contract.md`). Report the
measured cost per run from `output/runs/` rather than this cap.

**Illustrative scale (multiply out; these are not forecasts):**
| Segment | Assumption | Hours | Value at $36.14/h |
|---|---|---|---|
| Giving circles | 4,000 circles × one 3-charity decision a year × 4.5 h | 18,000 | about $0.65M a year |
| Family foundations | 38,701 (2009 count) × 10 grantee reviews a year × 1.5 h | about 580,500 | about $21.0M a year |
| Quality, not just time | 35% of donors research today (Money for Good); a 2-minute memo lowers the cost of checking at all | n/a | n/a |

**Quality evidence to cite alongside time.** The app's deterministic ratios can be checked against
`evals/ground-truth.csv`. For the 6 test charities with audited statements, total assets in the
extract match the audit within $843 and liabilities and net assets within 0.25%. MSF USA could only
be checked against ProPublica's own page, which matches the API exactly. Revenue and expense gaps of
up to about 5% come from GAAP versus 990 presentation, not extraction errors.

## 8. Additional verified studies on research time (added 2026-10-26)

Checked against the original PDFs on 2026-10-26 (text extracted and searched).

| Study | Finding (quoted or exact) | Source |
|---|---|---|
| Money for Good II, Hope Consulting with GuideStar (November 2011); 5,000+ individual donors, 800+ advisors, 700+ foundation grantmakers | "Foundations research 9 out of 10 grants, and on average spend 4 hours doing so"; "84% spend more than 1 hour researching (vs. 30% for individual donors)", "Median = 4 hours". Individual donors' researched gifts: 44% took 0 to 30 minutes, 26% 30 minutes to 1 hour, 15% 1 to 2 hours, 7% 2 to 6 hours. | https://www.multivu.com/players/English/52621-guidestar-and-hope-consulting-money-for-good-II/flexSwf/impAsset/document/38fdbdd6-68e7-479c-aa57-2dc3a09c78ff.pdf |
| Brown and Halvorsen, Boston College survey of midlevel donors (fielded April 2020; 1,260 Americans age 35+ who gave $2,000 to $20,000 in 2019) | Time spent on research: 34% less than 15 minutes, 33% 15 minutes to 1 hour, 33% more. "Only 1/3rd compared charities before donating (only 44% of those giving over $10,000 a year)". Why not: "25% say no time, don't know how, didn't think to do it; 43% already know" whom to support. 19% researched all donations. "57% of donors who give over $15,000 spent less than an hour on research." | https://www.sylviabrownsmartdonors.com/wp-content/uploads/sites/6/infographic.pdf |

**Reading.** Professional grantmakers, who do this for a living, spend a median of 4 hours per grant;
individual donors mostly spend under an hour and rarely compare. A quarter of midlevel donors who did
not compare said time or know-how stopped them, and 43% were already loyal to a charity, so the
realistic first users are donors choosing among new charities, giving circles and small foundations.
These two studies were first collected for a parallel build of this project and verified here.

## Source list (all accessed 2026-10-26)

- Giving USA 2026 summary, IU Lilly School: https://philanthropy.indianapolis.iu.edu/professional-development/blog/the-giving-usa-2026-report-deserves-a-closer-look.html
- Ohio CPA summary of Giving USA 2026: https://ohiocpa.com/for-the-public/news/2026/07/10/key-takeaways-from-giving-usa-on-2025-philanthropy-trends
- IRS Data Book FY2025 Table 2-6: https://www.irs.gov/pub/irs-soi/25db-2-06-eo.xlsx (index: https://www.irs.gov/statistics/soi-tax-stats-tax-exempt-organizations-and-nonexempt-charitable-trusts-irs-data-book-table-14)
- IRS Form 990 and instructions: https://www.irs.gov/pub/irs-pdf/f990.pdf ; https://www.irs.gov/pub/irs-pdf/i990.pdf
- Blackbaud Institute 2025 trends release: https://www.blackbaud.com/?p=45112
- GivingTuesday 2025 results: https://www.givingtuesday.org/blog/2025-results
- DAF Research Collaborative: https://www.dafresearchcollaborative.org/research/annual-daf-report
- Fidelity Charitable 2026 Giving Report: https://www.fidelitycharitable.org/insights/2026-giving-report.html
- DAFgiving360 2025 results (press release): https://www.businesswire.com/news/home/20260127969044/en/
- Collective giving: https://foundationsource.com/blog/collective-giving-is-on-the-rise-and-shifting-the-philanthropy-landscape/ ; https://johnsoncenter.org/resource/report-in-abundance-an-analysis-of-the-thriving-landscape-of-collective-giving-in-the-u-s/
- Family foundations (dated): https://candid.issuelab.org/resource/key-facts-on-family-foundations-2011 ; https://www.ncfp.org/resource/trends-research
- Money for Good: https://www.philanthropy.com/news/donors-value-charity-research-but-few-seek-it-out-report-finds/ ; https://blog.givewell.org/2010/07/20/the-money-for-good-study/ ; https://www.bridgespan.org/insights/donors-want-more-information-on-impact ; https://ssir.org/articles/entry/three_steps_to_more_informed_giving
- Give.org Donor Trust Report 2026: https://give.org/donor-trust-report/2026-trends-in-donor-trust-and-perspectives
- Candid AI and donors blog: https://candid.org/blogs/ai-and-fundraising-donors-search/
- Charity Navigator: https://www.charitynavigator.org/about-us/ ; https://www.charitynavigator.org/about-us/our-methodology/ratings/ ; methodology guide https://docs.google.com/document/d/1uIE5inGipHtqjhH1hM-8MiIBHqMXD5nSwA9F2bcXmT4/edit ; https://www.charitynavigator.org/about-us/news-thought-leadership/2023-reflections/ ; https://www.einpresswire.com/article/869704126/charity-navigator-launches-horizon-ai-search-powered-by-giving-compass-to-modernize-how-donors-find-nonprofits ; https://www.perplexity.ai/hub/blog/research-nonprofits-with-charity-navigator-on-perplexity
- CharityWatch: https://en.wikipedia.org/wiki/CharityWatch
- Candid: https://candid.org/pricing/ ; https://candid.org/press/candid-partners-with-anthropic-to-bring-trusted-data-to-claude-for-nonprofits/
- GiveWell: https://www.givewell.org/charities/top-charities ; Giving What We Can: https://www.givingwhatwecan.org/2025-evaluator-research
- ProPublica Nonprofit Explorer: https://projects.propublica.org/nonprofits/ ; https://projects.propublica.org/nonprofits/organizations/133433452
- BBB Wise Giving Alliance: https://give.org/news/inside-our-charity-evaluation-process ; https://give.org/bbb-standards-for-charity-accountability
- Fidelity Charitable research page: https://www.fidelitycharitable.org/guidance/research-charities.html
- ClearGiving: https://cleargiving.io/who-its-for
- Tow Center study: https://www.cjr.org/tow_center/we-compared-eight-ai-search-engines-theyre-all-bad-at-citing-news.php
- OpenAI deep research limitations (press coverage): https://www.verdict.co.uk/openai-launches-ai-research-agent/
- Overhead Myth: https://www.philanthropy.com/news/3-major-charity-groups-ask-donors-to-stop-focusing-on-overhead-costs/ ; https://www.charities.org/news/help-end-overhead-myth
- Nonprofit Starvation Cycle: https://ssir.org/articles/entry/the_nonprofit_starvation_cycle
- Impala due diligence anecdote: https://impala.digital/blog/how-a-major-foundation-cut-due-diligence-from-hours-to-clicks
- Independent Sector value of volunteer time: https://independentsector.org/research/value-of-volunteer-time/
