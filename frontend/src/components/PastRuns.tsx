import { useEffect, useState } from "react";
import type { Api } from "../api";
import type { RunSummary } from "../types";
import { cleanName, fmtCost, fmtDateTime, niceName } from "../format";
import { BandBadge, Notice, Spinner } from "./common";

function charityNames(r: RunSummary): { name: string; band?: string; overall?: number | null }[] {
  if (Array.isArray(r.charities) && r.charities.length) {
    return r.charities.map((c) => (typeof c === "string" ? { name: c } : { name: c.name ?? c.ein ?? "", band: c.band, overall: c.overall }));
  }
  if (Array.isArray(r.names)) return r.names.map((n) => ({ name: n }));
  if (Array.isArray(r.orgs)) return r.orgs.map((o) => ({ name: o.name ?? o.ein ?? "" }));
  return [];
}

function costOf(r: RunSummary): number | null {
  const c = r.cost_usd ?? r.total_cost_usd;
  if (typeof c === "number") return c;
  const usage = r.usage as { total?: { cost_usd?: number } } | undefined;
  return usage?.total?.cost_usd ?? null;
}

const STATUS_LABEL: Record<string, string> = { complete: "Complete", stopped_budget: "Stopped at budget", error: "Error" };

export function PastRuns({ api, onOpen }: { api: Api; onOpen: (runId: string) => void }) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .runs()
      .then(setRuns)
      .catch((e: Error) => setError(e.message));
  }, [api]);

  return (
    <div className="screen">
      <div className="screen-intro">
        <h1>Past runs</h1>
        <p className="lead">Open any saved memo, its run log, and its evidence ledger. Saved sample runs work without an API key.</p>
      </div>
      {error && <Notice tone="error" title="Could not load past runs">{error}</Notice>}
      {!runs && !error && (
        <p className="muted">
          <Spinner /> Loading...
        </p>
      )}
      {runs && runs.length === 0 && <p className="muted">No runs yet. Start one from step 1.</p>}
      {runs && runs.length > 0 && (
        <ul className="runs">
          {runs.map((r) => {
            const names = charityNames(r);
            const cost = costOf(r);
            return (
              <li key={r.run_id} className="run-item card">
                <div className="run-item-main">
                  <div className="run-item-top">
                    {r.sample && <span className="badge badge-sample">Saved sample run</span>}
                    <span className="muted small">{fmtDateTime(r.created_at)}</span>
                    {r.status && <span className="muted small">· {STATUS_LABEL[r.status] ?? r.status}</span>}
                    {cost != null && <span className="muted small">· {fmtCost(cost)}</span>}
                    {r.defenses_on === false && <span className="pill pill-bad">Defenses off</span>}
                  </div>
                  {r.headline && <h3 className="run-headline">{r.headline}</h3>}
                  <div className="run-charities">
                    {names.map((n, i) => (
                      <span key={i} className="run-charity">
                        {/\(DEMO\)/i.test(n.name) ? `${cleanName(n.name)} (DEMO)` : niceName(n.name)}
                        {n.band && <BandBadge band={n.band as never} />}
                      </span>
                    ))}
                  </div>
                  <div className="muted small mono">{r.run_id}</div>
                </div>
                <div className="run-item-actions">
                  <button className="btn btn-primary" type="button" onClick={() => onOpen(r.run_id)}>
                    Open memo
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
