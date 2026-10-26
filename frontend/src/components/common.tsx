import { createContext, useContext, useState, type ReactNode } from "react";
import type { Band, Evidence } from "../types";
import { BAND_HELP, BAND_LABELS, EVIDENCE_KIND_SHORT, evidenceKindFromId } from "../labels";
import { cleanName, niceName, truncate } from "../format";

export interface EvidenceCtx {
  evidence: Record<string, Evidence>;
  open: (id: string) => void;
}

export const EvidenceContext = createContext<EvidenceCtx>({ evidence: {}, open: () => undefined });

export function useEvidence() {
  return useContext(EvidenceContext);
}

export function DemoBadge() {
  return (
    <span className="badge badge-demo" title="Fictional charity used to test the app. Not a real organization.">
      DEMO
    </span>
  );
}

export function BandBadge({ band, large }: { band: Band; large?: boolean }) {
  return (
    <span className={`band band-${band}${large ? " band-lg" : ""}`} title={BAND_HELP[band]}>
      <span className="band-dot" aria-hidden />
      {BAND_LABELS[band]}
    </span>
  );
}

export function OrgName({ name, isDemo }: { name: string; isDemo: boolean }) {
  return (
    <>
      {isDemo ? cleanName(name) : niceName(name)}
      {isDemo && (
        <>
          {" "}
          <DemoBadge />
        </>
      )}
    </>
  );
}

/** A clickable source chip that opens the evidence drawer. */
export function SourceChip({ id }: { id: string }) {
  const { evidence, open } = useEvidence();
  const ev = evidence[id];
  const kind = ev?.kind ?? evidenceKindFromId(id);
  const text = ev ? chipText(ev) : id;
  return (
    <button
      type="button"
      className={`chip chip-${kind}${ev ? "" : " chip-missing"}`}
      onClick={() => open(id)}
      title={ev ? `${ev.label}: ${ev.display}` : `${id} (not in the evidence ledger)`}
    >
      <span className="chip-kind">{EVIDENCE_KIND_SHORT[kind]}</span>
      <span className="chip-text">{text}</span>
    </button>
  );
}

function chipText(ev: Evidence): string {
  if (ev.kind === "irs_field") {
    const label = ev.label.replace(/, tax year \d{4}$/, "");
    return truncate(`${label} ${ev.tax_year ?? ""}`.trim(), 34);
  }
  if (ev.kind === "web_excerpt") return truncate(ev.display || ev.label, 34);
  if (ev.kind === "user_input") return "Your note";
  return truncate(ev.label, 34);
}

export function SourceChips({ ids, limit }: { ids: string[]; limit?: number }) {
  const [expanded, setExpanded] = useState(false);
  if (!ids.length) return null;
  const hidden = limit && !expanded ? Math.max(0, ids.length - limit) : 0;
  const shown = hidden ? ids.slice(0, limit) : ids;
  return (
    <span className="chips">
      {shown.map((id) => (
        <SourceChip key={id} id={id} />
      ))}
      {hidden > 0 && (
        <button type="button" className="chip chip-more" onClick={() => setExpanded(true)} title="Show every source">
          +{hidden} more
        </button>
      )}
    </span>
  );
}

export function Card({ title, aside, children, className }: { title?: ReactNode; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className ?? ""}`}>
      {(title || aside) && (
        <header className="card-head">
          {title && <h3>{title}</h3>}
          {aside && <div className="card-aside">{aside}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Notice({ tone, title, children, action }: { tone: "info" | "warn" | "error" | "success"; title?: ReactNode; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className={`notice notice-${tone}`} role={tone === "error" ? "alert" : "status"}>
      <div className="notice-body">
        {title && <strong className="notice-title">{title}</strong>}
        {children && <div>{children}</div>}
      </div>
      {action && <div className="notice-action">{action}</div>}
    </div>
  );
}

export function Spinner() {
  return <span className="spinner" aria-hidden />;
}
