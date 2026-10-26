import { useState } from "react";
import type { Evidence } from "../types";
import { useEvidence } from "./common";

const MAX_YEARS = 5;

interface Point {
  id: string;
  value: number;
  display: string;
}

interface YearRow {
  year: number;
  revenue?: Point;
  expenses?: Point;
}

/** Total revenue and total expenses by tax year, read from the PP-<ein>-<year>-total_* ledger entries. */
export function trendRows(ein: string, evidence: Record<string, Evidence>): YearRow[] {
  const byYear = new Map<number, YearRow>();
  const prefix = `PP-${ein}-`;
  for (const ev of Object.values(evidence)) {
    if (!ev.id.startsWith(prefix) || ev.value === null || ev.value === undefined) continue;
    const m = /^PP-[^-]+-(\d{4})-total_(revenue|expenses)$/.exec(ev.id);
    if (!m) continue;
    const year = Number(m[1]);
    const row = byYear.get(year) ?? { year };
    row[m[2] as "revenue" | "expenses"] = { id: ev.id, value: ev.value, display: ev.display };
    byYear.set(year, row);
  }
  return [...byYear.values()].sort((a, b) => b.year - a.year).slice(0, MAX_YEARS).reverse();
}

function niceStep(range: number, target: number): number {
  const rough = range / target;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const norm = rough / mag;
  return (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
}

function axisMoney(v: number, step: number): string {
  if (v === 0) return "$0";
  const a = Math.abs(v);
  const [div, suffix] = a >= 1e9 ? [1e9, "B"] : a >= 1e6 ? [1e6, "M"] : a >= 1e3 ? [1e3, "K"] : [1, ""];
  const decimals = Math.min(2, Math.max(0, -Math.floor(Math.log10(step / div) + 1e-9)));
  return `${v < 0 ? "-" : ""}$${(a / div).toFixed(decimals)}${suffix}`;
}

function joinYears(ys: number[]): string {
  if (ys.length <= 1) return ys.join("");
  if (ys.length === 2) return `${ys[0]} and ${ys[1]}`;
  return `${ys.slice(0, -1).join(", ")}, and ${ys[ys.length - 1]}`;
}

const W = 400;
const H = 214;
const M = { top: 12, right: 14, bottom: 28, left: 50 };
const PAD_X = 20;

export function TrendChart({ ein, name }: { ein: string; name: string }) {
  const { evidence, open } = useEvidence();
  const [hover, setHover] = useState<number | null>(null);
  const rows = trendRows(ein, evidence);
  if (rows.length < 2) return null;

  const values = rows.flatMap((r) => [r.revenue?.value, r.expenses?.value]).filter((v): v is number => v !== undefined);
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (hi === lo) {
    lo = lo * 0.9;
    hi = hi * 1.1 || 1;
  }
  const step = niceStep(hi - lo, 4);
  const y0 = Math.max(lo >= 0 ? 0 : -Infinity, Math.floor(lo / step) * step);
  const y1 = Math.ceil(hi / step) * step;
  const ticks: number[] = [];
  for (let t = y0; t <= y1 + step / 2; t += step) ticks.push(t);

  const plotW = W - M.left - M.right;
  const plotH = H - M.top - M.bottom;
  const xAt = (i: number) => M.left + PAD_X + (rows.length === 1 ? 0 : (i * (plotW - 2 * PAD_X)) / (rows.length - 1));
  const yAt = (v: number) => M.top + plotH - ((v - y0) / (y1 - y0)) * plotH;
  const colW = (plotW - 2 * PAD_X) / Math.max(1, rows.length - 1);

  const path = (key: "revenue" | "expenses") => {
    let d = "";
    let pen = false;
    rows.forEach((r, i) => {
      const p = r[key];
      if (!p) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${xAt(i).toFixed(1)},${yAt(p.value).toFixed(1)} `;
      pen = true;
    });
    return d.trim();
  };

  const deficits = rows.filter((r) => r.revenue && r.expenses && r.expenses.value > r.revenue.value).map((r) => r.year);
  const latest = rows[rows.length - 1];
  const title = `Revenue and expenses, last ${rows.length} filings (IRS Form 990)`;
  const deficitText = deficits.length
    ? `Deficits (expenses above revenue) in ${joinYears(deficits)}.`
    : "No deficit years: revenue was at or above expenses in every year shown.";
  const latestText =
    latest.revenue || latest.expenses
      ? `Latest filing (${latest.year}): revenue ${latest.revenue?.display ?? "not reported"}, expenses ${latest.expenses?.display ?? "not reported"}.`
      : "";

  const point = (r: YearRow, i: number, key: "revenue" | "expenses") => {
    const p = r[key];
    if (!p) return null;
    const x = xAt(i);
    const y = yAt(p.value);
    const label = `Total ${key} ${r.year}: ${p.display}. Open the source.`;
    // Shrink the hit area when the two points of a year sit close together, so both stay clickable.
    const other = r[key === "revenue" ? "expenses" : "revenue"];
    const gap = other ? Math.abs(yAt(other.value) - y) : Infinity;
    const hitR = Math.max(5.5, Math.min(11, gap / 2));
    const activate = () => open(p.id);
    return (
      <g
        key={key}
        className={`trend-pt trend-pt-${key}`}
        role="button"
        tabIndex={0}
        aria-label={label}
        onClick={activate}
        onFocus={() => setHover(i)}
        onBlur={() => setHover(null)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            activate();
          }
        }}
      >
        <circle cx={x} cy={y} r={hitR} className="trend-hit" />
        {key === "revenue" ? <circle cx={x} cy={y} r={4.5} className="trend-mark" /> : <rect x={x - 4.5} y={y - 4.5} width={9} height={9} rx={1.5} className="trend-mark" />}
      </g>
    );
  };

  const hovered = hover === null ? null : rows[hover];
  // Put the tooltip beside the crosshair, away from the hovered points.
  let tipAlign = "";
  if (hovered && hover !== null) {
    const ys = [hovered.revenue, hovered.expenses].filter((p): p is Point => !!p).map((p) => yAt(p.value));
    const high = ys.length > 0 && Math.min(...ys) < M.top + plotH * 0.45;
    tipAlign = `${hover < rows.length / 2 ? " tip-after" : " tip-before"}${high ? " tip-low" : ""}`;
  }

  return (
    <figure className="trend-wrap" aria-label={`${title} for ${name}`}>
      <figcaption className="trend-head">
        <span className="trend-title">{title}</span>
        <span className="trend-legend" aria-hidden>
          <span className="lg lg-revenue">
            <svg width="22" height="10" viewBox="0 0 22 10">
              <line x1="1" y1="5" x2="21" y2="5" />
              <circle cx="11" cy="5" r="3.5" />
            </svg>
            Revenue
          </span>
          <span className="lg lg-expenses">
            <svg width="22" height="10" viewBox="0 0 22 10">
              <line x1="1" y1="5" x2="21" y2="5" />
              <rect x="7.5" y="1.5" width="7" height="7" rx="1" />
            </svg>
            Expenses
          </span>
          {deficits.length > 0 && (
            <span className="lg lg-deficit">
              <span className="lg-swatch" />
              Deficit year
            </span>
          )}
        </span>
      </figcaption>

      <div className="trend-plot" onMouseLeave={() => setHover(null)}>
        <svg className="trend" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}. ${deficitText} ${latestText}`}>
          {rows.map((r, i) =>
            deficits.includes(r.year) ? (
              <rect
                key={`d${r.year}`}
                x={Math.max(M.left + 1, xAt(i) - colW * 0.32)}
                y={M.top}
                width={Math.min(W - M.right - 1, xAt(i) + colW * 0.32) - Math.max(M.left + 1, xAt(i) - colW * 0.32)}
                height={plotH}
                rx={3}
                className="trend-deficit"
              />
            ) : null,
          )}
          {ticks.map((t) => (
            <g key={t}>
              <line x1={M.left} x2={W - M.right} y1={yAt(t)} y2={yAt(t)} className={t === y0 ? "trend-grid trend-base" : "trend-grid"} />
              <text x={M.left - 8} y={yAt(t) + 3.5} textAnchor="end" className="trend-ytick">
                {axisMoney(t, step)}
              </text>
            </g>
          ))}
          {rows.map((r, i) => (
            <text key={`y${r.year}`} x={xAt(i)} y={H - 8} textAnchor="middle" className={deficits.includes(r.year) ? "trend-xtick is-deficit" : "trend-xtick"}>
              {r.year}
            </text>
          ))}
          {hover !== null && <line x1={xAt(hover)} x2={xAt(hover)} y1={M.top} y2={M.top + plotH} className="trend-cross" />}
          <path d={path("expenses")} className="trend-line trend-line-expenses" />
          <path d={path("revenue")} className="trend-line trend-line-revenue" />
          {rows.map((r, i) => (
            <g key={`c${r.year}`} onMouseEnter={() => setHover(i)}>
              <rect x={xAt(i) - colW / 2} y={M.top} width={colW} height={plotH} className="trend-col" />
              {point(r, i, "expenses")}
              {point(r, i, "revenue")}
            </g>
          ))}
        </svg>
        {hovered && hover !== null && (
          <div className={`trend-tip${tipAlign}`} style={{ left: `${(xAt(hover) / W) * 100}%` }} role="presentation">
            <div className="tip-year">Tax year {hovered.year}</div>
            <div className="tip-row">
              <span className="tip-key tip-revenue" />
              Revenue <strong>{hovered.revenue?.display ?? "not reported"}</strong>
            </div>
            <div className="tip-row">
              <span className="tip-key tip-expenses" />
              Expenses <strong>{hovered.expenses?.display ?? "not reported"}</strong>
            </div>
            {deficits.includes(hovered.year) && <div className="tip-note">Expenses above revenue</div>}
          </div>
        )}
      </div>

      <p className="trend-summary">
        {deficitText} {latestText}
        <span className="no-print"> Click a point to see its source.</span>
      </p>
    </figure>
  );
}
