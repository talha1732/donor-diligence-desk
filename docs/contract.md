# Build contract: Donor Diligence Desk

Read `AGENTS.md` first. This file fixes the interfaces so several builders can work in parallel.
Shared models are in `backend/app/schemas.py` (frozen). Python package root is `backend/`, so
imports look like `from app.schemas import ...` and tests run with `backend/` on `sys.path`
(`backend/tests/conftest.py` does that; see also section 12).

## 1. Repository layout

```
mgt409-final-project/
  AGENTS.md  README.md  .env.example  .gitignore
  docs/            contract.md, decision-log.md, scoring-rubric.md, safety.md, research.md
  backend/
    run.py                 entry point: serves API + built UI on http://127.0.0.1:8000
    requirements.txt       runtime deps (staff install this)
    requirements-dev.txt   + pytest
    app/
      schemas.py           frozen shared models
      config.py            settings, .env discovery, Portkey model builder
      main.py              FastAPI routes, SSE, static UI, /demo pages
      events.py            event bus + traced agent runner
      orchestrator.py      the run pipeline (section 7)
      agents/              financial.py, impact.py, auditor.py, memo.py
      prompts/             financial.md, impact.md, auditor.md, memo.md
      tools/               propublica.py, financials.py, scoring.py, web.py
      safety/              sanitize.py, injection.py, verify.py, guards.py
      cost/                pricing.py, budget.py
      audit.py             audit trail writer
    data/
      cache/propublica/    committed API cache + demo fixtures (offline test dataset)
      demo_pages/          local demo charity websites, incl. a booby-trapped one
    tests/
  frontend/                React + Vite + TS; `npm run build` -> frontend/dist (committed)
  evals/                   evaluation scripts and ground truth
  output/                  audit_trail.jsonl, runs/<run_id>.json, daily_spend.json (gitignored)
```

## 2. Settings (environment variables, all optional except the key)

| Variable | Default | Meaning |
|---|---|---|
| `PORTKEY_API_KEY` | (required for live runs) | Course key. Read from `.env` in repo root, then each parent folder; nearest wins. |
| `MODEL_NAME` | `gpt-6-luna` | Only luna is allowed on the course key. |
| `PORTKEY_BASE_URL` | `https://api.portkey.ai/v1` | |
| `PORT` | `8000` | |
| `RUN_BUDGET_USD` | `0.10` | Default per-run cap. Requests may lower it, or raise it up to `MAX_RUN_BUDGET_USD`. |
| `MAX_RUN_BUDGET_USD` | `0.50` | |
| `DAILY_BUDGET_USD` | `2.00` | Global cap across all runs per calendar day. |
| `RATE_LIMIT_PER_MIN` | `5` | Diligence runs per client IP per minute. |
| `OFFLINE_MODE` | `0` | `1` = ProPublica from cache only, web fetch only for /demo pages. |
| `ALLOW_DEFENSE_TOGGLE` | `0` | `1` = the request flag `defenses_off` is honoured (safety demo and evals only). |

Portkey model builder (same pattern as the course repos):

```python
client = AsyncOpenAI(api_key=PORTKEY_API_KEY, base_url=PORTKEY_BASE_URL,
                     default_headers={"x-portkey-provider": "openai"})
model = OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
```

gpt-6-luna needs the Responses API for function tools.

## 3. ProPublica field mapping (raw filing -> `FilingYear`)

Form 990 (`formtype` 0):

| FilingYear | Raw field |
|---|---|
| tax_year | `tax_prd_yr` |
| tax_period | `tax_prd` |
| form_type | `formtype`: 0 -> "990", 1 -> "990EZ", 2 -> "990PF" |
| pdf_url | `pdf_url` |
| total_revenue | `totrevenue` |
| total_expenses | `totfuncexpns` |
| total_assets | `totassetsend` |
| total_liabilities | `totliabend` |
| net_assets | `totnetassetend` |
| contributions | `totcntrbgfts` |
| program_service_revenue | `totprgmrevnue` |
| investment_income | `invstmntinc` |
| officer_compensation | `compnsatncurrofcr` |
| other_salaries | `othrsalwages` |
| payroll_tax | `payrolltx` |
| professional_fundraising_fees | `profndraising` |
| fundraising_event_gross | `grsincfndrsng` |
| fundraising_event_direct_expenses | `lessdirfndrsng` |

990EZ and 990PF filings use different raw names. Map what clearly corresponds (inspect the raw
keys in a real response) and leave the rest `None`. Never fill a missing value with 0.

## 4. Metric keys and formulas (`tools/financials.py`)

"Latest" means the newest filing with data. Each metric gets a `CALC-<ein>-<key>` evidence entry whose
`inputs` lists the `PP-...` ids used and whose `excerpt` states the formula in words.
When a metric cannot be computed, `value=None` and `reason_missing` says why.

| key | unit | formula |
|---|---|---|
| total_revenue_latest | usd | latest total_revenue |
| total_expenses_latest | usd | latest total_expenses |
| surplus_margin | ratio | (revenue - expenses) / revenue, latest; None if revenue <= 0 |
| avg_surplus_margin_3y | ratio | mean surplus margin over up to 3 newest years (needs >= 2) |
| net_assets_months | months | net_assets / (expenses / 12), latest. Label it a reserves proxy. |
| liabilities_to_assets | ratio | liabilities / assets, latest; None if assets <= 0 |
| revenue_cagr_3y | ratio | (rev_latest / rev_k)^(1/k) - 1, k = gap in years to the filing about 3 years back (k >= 2) |
| expense_cagr_3y | ratio | same for expenses |
| revenue_volatility_cv | ratio | stdev / mean of revenue over up to 5 newest years (needs >= 3) |
| contributions_share | ratio | contributions / revenue, latest |
| revenue_concentration_hhi | ratio | sum of squared shares of contributions, program service revenue, investment income, and other (revenue minus those three, floored at 0), latest |
| officer_comp_share | ratio | officer_compensation / expenses, latest |
| staff_cost_share | ratio | (officer_compensation + other_salaries + payroll_tax) / expenses, latest |
| pro_fundraising_fee_share | ratio | professional_fundraising_fees / contributions; None if contributions <= 0 |
| filing_recency_years | years | current calendar year minus latest tax_year |
| years_of_filings | count | number of filings with data |
| program_expense_share | ratio | ALWAYS None. reason_missing: "Not in the free IRS extract (Form 990 Part IX, column B). Ask the charity or read the filing PDF." |

Display strings: usd as `$3.22B`, `$41.5M`, `$812K`, `$9,450`; ratio as `12.4%`; months as `7.1 months`.

## 5. Scoring (`tools/scoring.py`, documented in `docs/scoring-rubric.md`)

Five dimensions, each 0-100 or None:

| Dimension | Inputs |
|---|---|
| financial_health | surplus_margin and avg_surplus_margin_3y, net_assets_months, liabilities_to_assets |
| revenue_resilience | revenue_concentration_hhi, revenue_volatility_cv, revenue_cagr_3y |
| cost_discipline | officer_comp_share, pro_fundraising_fee_share, expense_cagr_3y versus revenue_cagr_3y |
| transparency | filing_recency_years, years_of_filings, impact.publishes_financials, impact.publishes_outcomes |
| impact_evidence | impact.evidence_level 0-4 mapped to 0/25/50/75/100; None if no impact assessment |

Overall is the weighted mean of non-None dimensions (all-zero weights mean equal weights).
Bands: overall >= 70 `strong_fit`; 50 to under 70 `fit_with_questions`; under 50 `weak_fit`;
`insufficient_data` when two or more dimensions are None or there are no filings.
Each DimensionScore lists its driver evidence ids and a one-sentence plain explanation.
Thresholds are a documented rubric (hypothesis), anchored where possible to Charity Navigator's
published Encompass financial metrics; say so in the rubric doc.

## 6. Claim verification rules (`safety/verify.py`)

- Strip evidence ids (e.g. `PP-530196605-2023-total_revenue`) from text before extracting numbers.
- Extract: currency (`$1.2M`, `$1,200,000`, `$3.2 billion`, `1.2 million dollars`), percents
  (`12.4%`, `12 percent`), months (`7.1 months`), counts/years (`3 years`), and other plain numbers.
- Ignore four-digit years 1990-2035 (tax years, "FY2023"), and numbers written as words.
- A number matches an evidence entry when units are compatible and it is within tolerance:
  - usd vs usd evidence: relative difference <= 2%, or within half a unit of the last digit shown
    (`$3.2B` matches 3,217,077,611).
  - percent vs ratio evidence: compare claim/100 with the ratio; abs difference <= 0.5 percentage
    points or half a unit of the last digit shown.
  - months / years / count: abs difference <= max(0.5, 2%).
  - plain numbers >= 1000 may match usd evidence; small plain numbers may match count evidence.
- Search the finding's cited `evidence_ids` first. If not found there, search other evidence for the
  same EIN; a match there counts as verified and the id is added to the finding's evidence_ids.
- Status: no numbers -> `no_numbers`; all matched -> `verified`; cites an id not in the ledger ->
  `unknown_evidence_id`; any number unmatched -> `unverified_number`; has numbers but no
  evidence_ids and no same-EIN match -> `missing_evidence`.
- Orchestrator policy with defenses on: findings with `unverified_number`, `unknown_evidence_id`, or
  `missing_evidence` are removed from the memo, listed under "could not verify", and produce a
  `SecurityEvent(kind="unverified_claim")`. With defenses off they are kept.
- `verify_text` checks memo free text (headline, summary, recommendation, one_line) against all run
  evidence. With defenses on, sentences with unmatched numbers are removed.

## 7. Run pipeline and agents (`orchestrator.py`, `agents/`)

1. **Intake (no LLM):** `guards.screen_request`, daily budget check, `propublica.get_org_profile`
   for each EIN, `financials.build_irs_evidence` + `compute_metrics`. Emit evidence.
2. **Research (parallel):** for each charity run `financial:<ein>` and `impact:<ein>` concurrently.
3. **Verification (no LLM):** `verify.verify_findings` on all findings.
4. **Audit:** `auditor` agent reviews findings plus their verification status and security events.
5. **Scoring (no LLM):** `scoring.score_charity` per charity.
6. **Memo:** `memo` agent writes `MemoAgentOutput` referencing finding ids; orchestrator assembles
   `GivingMemo` from verified findings only, then runs `verify_text` on the free text.
7. **Finish:** `audit.append_run`, emit `final`.

| Agent key | Role label | Tools | Limits (requests / tool calls) | Output type |
|---|---|---|---|---|
| `financial:<ein>` | Financial Analyst | `get_field_history(field)`, `get_metric(key)`, `compare_years(field, year_a, year_b)` (registers a new CALC evidence id for the change) | 6 / 8 | `FinancialAgentOutput` |
| `impact:<ein>` | Impact Researcher | `search_web(query)` (max 2), `read_page(url)` (max 3; check_url, fetch_url, sanitize_html, redact_injections, wrap_untrusted; each page adds WEB evidence) | 8 / 6 | `ImpactAgentOutput` |
| `auditor` | Red-Team Auditor | `get_evidence(evidence_id)` | 4 / 6 | `AuditorAgentOutput` |
| `memo` | Memo Writer | none | 3 / 0 | `MemoAgentOutput` |

- Each agent: per-agent timeout 90 s; whole run 240 s.
- Budget: every model response updates `BudgetTracker`; on `BudgetExceeded` cancel remaining agents,
  emit `security` (budget_stop), and return a partial result with status `stopped_budget`.
- Prompt caching: put the long, stable instructions first and identical across calls (system prompt
  over 1024 tokens so OpenAI automatic prompt caching applies); put per-charity data in the user
  prompt. Report cached tokens from the API's usage fields. Never fake cache numbers.
- An agent error must not crash the run: its report gets `status="error"` and scoring proceeds with
  what exists.
- With defenses off (only when `ALLOW_DEFENSE_TOGGLE=1`): skip sanitize/redact/wrap, skip removal of
  unverified claims, and skip donor-note screening. Everything else (budget, limits) stays on.

## 8. Server-sent events (`POST /api/diligence/stream`)

Each SSE message: `event: <type>` and `data: {"type": ..., "ts": ISO, "data": {...}}`.

| type | data |
|---|---|
| `run_started` | `{run_id, model, budget_usd, defenses_on, charities: [{ein, name, is_demo}], weights}` |
| `stage` | `{stage: "intake"|"research"|"verify"|"audit"|"scoring"|"memo", status: "started"|"done"}` |
| `agent_started` | `{agent, role, ein, label}` |
| `agent_step` | `{agent, ein, step, kind: "model_request"|"model_response"|"end", text?, tool_calls?, usage?}` |
| `tool_call` | `{agent, ein, tool, args, result_summary, ms}` |
| `evidence_added` | `{ids: [...], count}` |
| `security` | `SecurityEvent` |
| `spend` | `RunUsage` |
| `agent_done` | `{agent, ein, status, usage: AgentUsage, summary}` |
| `final` | `DiligenceResult` |
| `error` | `{message, partial: DiligenceResult or null}` |

## 9. HTTP API (`main.py`)

| Method and path | Response |
|---|---|
| `GET /api/health` | `{ok, model, portkey_key_set, offline_mode, allow_defense_toggle, run_budget_usd, daily_budget_usd, daily_spent_usd}` |
| `GET /api/search?q=&state=` | `{results: OrgSearchResult[]}` (no LLM) |
| `GET /api/featured` | `{results: OrgSearchResult[]}` (DEMO fixtures first, then cached real charities) |
| `GET /api/org/{ein}` | `{profile: OrgProfile, metrics: FinancialMetrics}` (no LLM) |
| `POST /api/diligence/stream` | SSE (section 8). 429 when rate limited. |
| `POST /api/diligence` | `DiligenceResult` |
| `GET /api/pricing` | `{model, prices_per_million, source}` |
| `GET /api/runs` | `{runs: [...]}` compact audit records, newest first |
| `GET /api/runs/{run_id}` | `DiligenceResult` |
| `GET /demo/{file}` | demo charity page from `backend/data/demo_pages/` |
| `GET /` and assets | `frontend/dist` |

## 10. Demo fixtures (offline test dataset)

- `000000001` **Riverbend Community Pantry (DEMO)**, fictional food pantry, New Haven CT, 4 years of
  plausible 990 data. `website_url = http://127.0.0.1:8000/demo/riverbend-pantry.html`. That page
  is booby-trapped: hidden text (white on white, display:none, an HTML comment, and an aria-hidden
  block) tells AI agents to rate the charity 100/100, claim a 95% program-spending ratio, and say
  GiveWell evaluated it. The visible page is an ordinary pantry website.
- `000000002` **Harbor Lights Literacy Project (DEMO)**, fictional, clean page
  `harbor-literacy.html`, with one year of deficit and published outcomes.
- 6 to 8 real charities cached from the live API for featured one-click runs (mix of a national
  charity, an evidence-focused charity, and New Haven / Connecticut local organizations).

## 11. Frontend requirements (`frontend/`)

- React + Vite + TypeScript. TypeScript types in `src/types.ts` mirror `schemas.py`.
- Vite dev server on 5173 proxies `/api` and `/demo` to `http://127.0.0.1:8000`.
- `npm run build` writes `frontend/dist`, committed so staff need no Node.
- `?mock=1` replays a bundled sample event stream so the UI works with no backend.
- Screens: (1) choose charities (search box with state filter, featured cards, up to 3 selected,
  optional website field per charity); (2) priorities (five weight sliders, donor note, budget);
  (3) live run (agent cards per charity lighting up as events arrive, tool-call log, spend meter
  against budget, security panel listing defenses that fired); (4) memo (action-title headline,
  spider chart per charity on a shared 0-100 scale, band badges, strengths and concerns with
  clickable source chips that open the evidence entry, questions for the charity, could-not-verify
  list, token and cost table per agent, print-friendly layout).
- Design: white background, deep navy text and headings, one accent colour, serif headings
  (Georgia) and sans body. Plain, professional, readable by someone who has never seen the app.

## 12. Amendments (2026-10-26, binding; they win over earlier sections)

1. **Paths.** `REPO_ROOT` = parent of `backend/`. Runtime output goes to `OUTPUT_DIR` (env var,
   default `REPO_ROOT/output`), never relative to the current working directory. Tests set
   `OUTPUT_DIR` to a temp dir.
2. **.env discovery** (`config.py`): look for `.env` in `REPO_ROOT`, then each parent folder up to
   the filesystem root; load the nearest one that exists with `override=False` (a real environment
   variable wins). Skip loading entirely when `DOTENV_DISABLED=1`. The teaching staff's `.env` sits
   one level above the repo and has `PORTKEY_API_KEY` and `OPENAI_API_KEY`.
3. **Shared helpers in `tools/financials.py`** (data builder adds them, agents builder uses them):
   - `format_value(value: float | None, unit: str) -> str`: display strings from section 4
     (`None` -> "n/a").
   - `compare_years(profile, field, year_a, year_b) -> Evidence | None`: deterministic change
     between two tax years for one FilingYear field. Id `CALC-<ein>-<field>-chg-<year_a>-<year_b>`,
     unit ratio (percent change), `inputs` = the two PP ids, display like `+12.4% (2021 to 2023)`.
     None when either value is missing or the base is <= 0.
4. **Run event log.** The orchestrator keeps every SSE event dict (same shape as section 8) in order.
   `audit.append_run(result, events=None)` writes `OUTPUT_DIR/runs/<run_id>.json` (DiligenceResult),
   `OUTPUT_DIR/runs/<run_id>.events.jsonl` (one event per line) and appends the compact line to
   `OUTPUT_DIR/audit_trail.jsonl`. `audit.load_events(run_id) -> list[dict] | None`.
   New route: `GET /api/runs/{run_id}/events` -> `{events: [...]}` (404 if unknown).
   `agent_step.text` is truncated to 600 characters in events.
5. **Frontend URL parameters** (for screenshots and the report's step-by-step run trace):
   - `?mock=1` replays the bundled sample stream (no backend needed).
   - `?replay=<run_id>&speed=<n>` fetches `/api/runs/<run_id>/events` and replays them on the live
     run screen (default speed 4x; `speed=0` shows the end state immediately).
   - `?run=<run_id>` opens the memo of a saved run; `&tab=run` shows its live-run screen in the end
     state; `&tab=evidence` shows the evidence ledger.
   - After a run, the user can switch between the memo and the run log (agents, tool calls, spend,
     security) without losing state.
   Pages must look right at 1440x900 and print cleanly.
6. **Frontend stack** stays React + Vite + TypeScript; `frontend/dist` is committed. No CDN at runtime
   (the app must work offline for the demo fixtures).
7. **Dev environment** is macOS; see AGENTS.md section 3.
