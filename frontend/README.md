# Donor Diligence Desk: frontend

React + Vite + TypeScript. No UI or chart libraries; the spider chart is plain SVG. System fonts only
(Georgia for headings, the system sans for body), and nothing is loaded from the internet at runtime.

The built app in `frontend/dist/` is committed, so the teaching staff only need Python:
`python backend/run.py` serves it at http://127.0.0.1:8000. Node is only needed to change the UI.

## Develop

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api and /demo to http://127.0.0.1:8000
```

Start the backend in another terminal (`python backend/run.py`) for live runs. Without a backend, use mock mode.

## Build

```bash
npm run typecheck    # tsc, no emit
npm run build        # type-checks, then writes frontend/dist (asset paths are relative)
```

Commit `frontend/dist/` after every UI change.

## URL parameters

| URL | What it does |
|---|---|
| `?mock=1` | Replays the bundled sample run (`src/mock/sampleEvents.ts`) on the live-run screen. No backend or key needed. Default speed 4x. |
| `?mock=1&speed=0` | Same, but jumps straight to the finished state. |
| `?mock=1&step=1` / `step=2` | Opens step 1 (choose charities) or step 2 (priorities) with mock data and two charities preselected. Start replays the sample run. Add `&q=food&state=CT` to step 1 to prefill a search. |
| `?mock=1&step=runs` | Past runs list with the bundled sample run. |
| `?replay=<run_id>&speed=<n>` | Fetches `/api/runs/<run_id>/events` and replays them on the live-run screen (default 4x, `speed=0` shows the end state). |
| `?run=<run_id>` | Opens the memo of a saved run (`/api/runs/<run_id>`, plus its event log when available). |
| `&tab=memo` / `&tab=run` / `&tab=evidence` | Works with `run`, `replay`, and `mock`: shows the memo, the run log, or the evidence ledger. |

After a live run finishes the address bar changes to `?run=<run_id>&tab=...`, so a reload or a shared link reopens it.

## Screens

1. **Choose charities**: search (`GET /api/search?q=&state=`), featured cards (`GET /api/featured`, DEMO first), up to three, optional website per charity.
2. **Set priorities**: five weights 0 to 5, donor note (500 characters), spending cap (default from `/api/health`, max $0.50).
3. **Watch the run / Run log**: `POST /api/diligence/stream` read with `fetch` and a stream reader (SSE over POST). Stage stepper, one card per agent, tool-call log, spend meter, safety panel.
4. **Read the memo**: headline, summary, recommendation, at-a-glance table, per-charity spider chart, dimension explanations, strengths and concerns with source chips, questions, could-not-verify list, auditor notes, token and cost table. Prints cleanly (browser print or "Print or save as PDF").
   - **Try different priorities**: five weight sliders under the at-a-glance table re-rank the charities instantly in the browser (`src/reweight.ts` mirrors `backend/app/tools/scoring.py`: weighted mean, all-zero weights count equally, `band_for` thresholds and the insufficient-data rule). No AI calls. Print shows the original priorities only.
   - **Revenue and expenses chart** per charity (`src/components/TrendChart.tsx`): up to the 5 most recent tax years from the `PP-<ein>-<year>-total_revenue` / `total_expenses` ledger entries, deficit years marked, each point opens its evidence entry. Hidden when fewer than 2 years exist.
   - **Draft an email to the charity** (`src/components/EmailDraft.tsx`): a fixed, editable template with the questions, "Copy email" and a `mailto:` link. Hidden in print.

The evidence ledger tab lists every evidence entry with filters. Source chips anywhere open a side drawer with the entry, its formula or quote, its inputs (as further chips), and its source link.

## Files

- `src/types.ts` mirrors `backend/app/schemas.py` and the SSE events in `docs/contract.md` section 8.
- `src/runState.ts` turns events into screen state; `src/player.ts` replays recorded events.
- `src/api.ts` has the live API client (including the SSE parser) and the mock API.
- `src/mock/sampleEvents.ts` builds the sample run. IRS figures come from the Riverbend DEMO fixture and the cached Connecticut Foodshare filings; metrics are computed with the contract formulas. Website excerpts, agent text, and scores are sample data.
