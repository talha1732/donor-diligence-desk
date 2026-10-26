import { useEffect, useMemo, useRef, useState } from "react";
import type { DiligenceResult, Evidence, EvidenceKind } from "../types";
import { EVIDENCE_KIND_LABELS, EVIDENCE_KIND_SHORT, evidenceKindFromId } from "../labels";
import { cleanName, niceName } from "../format";
import { SourceChip, useEvidence } from "./common";

function sourceLabel(url: string): string {
  if (url.startsWith("fixture:")) return "Bundled demo fixture";
  try {
    const u = new URL(url, window.location.href);
    if (u.hostname.includes("propublica.org")) return "ProPublica Nonprofit Explorer";
    return u.hostname + (u.pathname !== "/" ? u.pathname : "");
  } catch {
    return url;
  }
}

/** Side drawer with one evidence entry. Inputs are chips that navigate within the drawer. */
export function EvidenceDrawer({ stack, onClose, onBack, orgName }: { stack: string[]; onClose: () => void; onBack: () => void; orgName: (ein: string | null | undefined) => string }) {
  const { evidence } = useEvidence();
  const id = stack[stack.length - 1];
  const ev: Evidence | undefined = id ? evidence[id] : undefined;
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!id) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [id, onClose]);

  if (!id) return null;
  const kind = ev?.kind ?? evidenceKindFromId(id);
  const isLink = ev?.source_url && /^https?:/i.test(ev.source_url);

  return (
    <div className="drawer-layer no-print" role="dialog" aria-modal="true" aria-label="Evidence entry">
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer">
        <header className="drawer-head">
          <div>
            {stack.length > 1 && (
              <button className="btn-link" type="button" onClick={onBack}>
                Back
              </button>
            )}
            <div className="eyebrow">Evidence entry</div>
          </div>
          <button ref={closeRef} className="btn-icon" type="button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        <div className="drawer-body">
          <span className={`kind-tag kind-${kind}`}>
            {EVIDENCE_KIND_SHORT[kind]} · {EVIDENCE_KIND_LABELS[kind]}
          </span>
          {!ev ? (
            <>
              <h2>Not in the evidence ledger</h2>
              <p>
                The id <code>{id}</code> was cited but no matching entry exists. Claims that cite unknown ids are removed from
                the memo when defenses are on.
              </p>
            </>
          ) : (
            <>
              <h2>{ev.label}</h2>
              <div className="ev-display">{ev.display}</div>
              <dl className="ev-meta">
                {ev.ein && (
                  <div>
                    <dt>Charity</dt>
                    <dd>{orgName(ev.ein)}</dd>
                  </div>
                )}
                {ev.tax_year != null && (
                  <div>
                    <dt>Tax year</dt>
                    <dd>{ev.tax_year}</dd>
                  </div>
                )}
                {ev.value != null && ev.unit !== "text" && (
                  <div>
                    <dt>Raw value</dt>
                    <dd className="mono">
                      {ev.value.toLocaleString("en-US", { maximumFractionDigits: 6 })} <span className="muted">({ev.unit})</span>
                    </dd>
                  </div>
                )}
                <div>
                  <dt>Evidence id</dt>
                  <dd className="mono small break-id">{ev.id}</dd>
                </div>
              </dl>
              {ev.excerpt && (
                <div className="ev-section">
                  <h3>{kind === "calculation" ? "Formula" : kind === "web_excerpt" ? "Quoted from the page" : kind === "user_input" ? "What you wrote" : "Source field"}</h3>
                  {kind === "web_excerpt" || kind === "user_input" ? <blockquote className="quote">{ev.excerpt}</blockquote> : <p>{ev.excerpt}</p>}
                  {kind === "web_excerpt" && <p className="muted small">Website text is self-reported by the charity and was sanitized before any agent read it.</p>}
                </div>
              )}
              {ev.inputs.length > 0 && (
                <div className="ev-section">
                  <h3>Inputs ({ev.inputs.length})</h3>
                  <div className="chips chips-col">
                    {ev.inputs.map((i) => (
                      <SourceChip key={i} id={i} />
                    ))}
                  </div>
                </div>
              )}
              {ev.source_url && (
                <div className="ev-section">
                  <h3>Source</h3>
                  {isLink ? (
                    <a href={ev.source_url} target="_blank" rel="noreferrer noopener">
                      {sourceLabel(ev.source_url)}
                    </a>
                  ) : (
                    <span>{sourceLabel(ev.source_url)}</span>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

const KINDS: EvidenceKind[] = ["irs_field", "calculation", "web_excerpt", "user_input"];

export function EvidenceLedger({ result, evidence }: { result: DiligenceResult | null; evidence: Record<string, Evidence> }) {
  const { open } = useEvidence();
  const [ein, setEin] = useState("all");
  const [kind, setKind] = useState<EvidenceKind | "all">("all");
  const [q, setQ] = useState("");
  const all = useMemo(() => Object.values(evidence), [evidence]);
  const orgs = result?.orgs ?? [];
  const nameOf = (e: string | null | undefined) => {
    if (!e) return "Run";
    const o = orgs.find((x) => x.ein === e);
    return o ? (o.is_demo ? cleanName(o.name) : niceName(o.name)) : e;
  };
  const counts = useMemo(() => {
    const c: Record<string, number> = { all: 0 };
    for (const e of all) {
      if (ein !== "all" && (e.ein ?? "none") !== ein) continue;
      c.all += 1;
      c[e.kind] = (c[e.kind] ?? 0) + 1;
    }
    return c;
  }, [all, ein]);
  const rows = all.filter(
    (e) =>
      (ein === "all" || (e.ein ?? "none") === ein) &&
      (kind === "all" || e.kind === kind) &&
      (!q || `${e.id} ${e.label} ${e.display} ${e.excerpt ?? ""}`.toLowerCase().includes(q.toLowerCase())),
  );

  return (
    <div className="screen">
      <div className="screen-intro">
        <h1>Evidence ledger</h1>
        <p className="lead">
          Every number in the memo traces to one of these entries: an IRS Form 990 field, a deterministic calculation, a
          quoted website excerpt, or your own note. Click a row to see its source and inputs.
        </p>
      </div>
      <div className="filters">
        <label className="field">
          <span className="field-label">Charity</span>
          <select value={ein} onChange={(e) => setEin(e.target.value)}>
            <option value="all">All charities</option>
            {orgs.map((o) => (
              <option key={o.ein} value={o.ein}>
                {nameOf(o.ein)}
              </option>
            ))}
            {all.some((e) => !e.ein) && <option value="none">Not tied to a charity</option>}
          </select>
        </label>
        <div className="field">
          <span className="field-label">Kind</span>
          <div className="segmented" role="group">
            <button type="button" className={kind === "all" ? "on" : ""} onClick={() => setKind("all")}>
              All <span className="seg-count">{counts.all ?? 0}</span>
            </button>
            {KINDS.map((k) => (
              <button key={k} type="button" className={kind === k ? "on" : ""} onClick={() => setKind(k)}>
                {EVIDENCE_KIND_LABELS[k]} <span className="seg-count">{counts[k] ?? 0}</span>
              </button>
            ))}
          </div>
        </div>
        <label className="field grow">
          <span className="field-label">Filter text</span>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="For example: revenue, 2023, margin" />
        </label>
      </div>
      <div className="card flush">
        <div className="table-wrap">
          <table className="table ledger">
            <thead>
              <tr>
                <th>Kind</th>
                <th>Charity</th>
                <th>What it is</th>
                <th className="num">Value</th>
                <th>Year</th>
                <th>Evidence id</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id} className="clickable" onClick={() => open(e.id)} tabIndex={0} onKeyDown={(k) => k.key === "Enter" && open(e.id)}>
                  <td>
                    <span className={`kind-tag kind-${e.kind}`}>{EVIDENCE_KIND_SHORT[e.kind]}</span>
                  </td>
                  <td className="nowrap">{nameOf(e.ein)}</td>
                  <td>{e.tax_year ? e.label.replace(new RegExp(`,? (tax year|fiscal year|FY) ?${e.tax_year}$`, "i"), "") : e.label}</td>
                  <td className="num nowrap">{e.display}</td>
                  <td>{e.tax_year ?? ""}</td>
                  <td className="mono small muted break-id">{e.id}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted center">
                    No entries match these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      <p className="muted small">
        Showing {rows.length} of {all.length} entries.
      </p>
    </div>
  );
}
