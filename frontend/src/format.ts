import type { Unit } from "./types";

/** Display strings from contract section 4: $3.22B, $41.5M, $812K, $9,450. */
export function fmtUsd(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  const sign = v < 0 ? "-" : "";
  const a = Math.abs(v);
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e4) return `${sign}$${Math.round(a / 1e3)}K`;
  return `${sign}$${Math.round(a).toLocaleString("en-US")}`;
}

export function fmtPct(ratio: number | null | undefined, digits = 1): string {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return "n/a";
  return `${(ratio * 100).toFixed(digits)}%`;
}

export function fmtValue(v: number | null | undefined, unit: Unit): string {
  if (v === null || v === undefined) return "n/a";
  switch (unit) {
    case "usd":
      return fmtUsd(v);
    case "ratio":
      return fmtPct(v);
    case "months":
      return `${v.toFixed(1)} months`;
    case "years":
      return `${Number.isInteger(v) ? v : v.toFixed(1)} years`;
    case "count":
      return Math.round(v).toLocaleString("en-US");
    default:
      return String(v);
  }
}

export function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined) return "0";
  return Math.round(v).toLocaleString("en-US");
}

/** Run costs are fractions of a cent, so show four decimals below $1. */
export function fmtCost(v: number | null | undefined): string {
  if (v === null || v === undefined) return "$0.0000";
  if (v >= 1) return `$${v.toFixed(2)}`;
  return `$${v.toFixed(4)}`;
}

export function fmtSeconds(v: number | null | undefined): string {
  if (v === null || v === undefined) return "0.0 s";
  return `${v.toFixed(1)} s`;
}

export function fmtEin(ein: string): string {
  const d = ein.replace(/\D/g, "").padStart(9, "0");
  return `${d.slice(0, 2)}-${d.slice(2)}`;
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

/** Demo fixtures carry "(DEMO)" in their name; the UI shows a badge instead. */
export function cleanName(name: string): string {
  return name.replace(/\s*\(DEMO\)\s*$/i, "").trim();
}

/** ProPublica names are often upper case ("CONNECTICUT FOODSHARE INC"); title-case those only. */
export function niceName(name: string): string {
  const n = cleanName(name);
  if (n !== n.toUpperCase()) return n;
  const small = new Set(["of", "and", "the", "for", "in", "on", "at", "to", "a"]);
  return n
    .toLowerCase()
    .split(/\s+/)
    .map((w, i) => (i > 0 && small.has(w) ? w : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

export function truncate(s: string | null | undefined, n: number): string {
  if (!s) return "";
  return s.length > n ? `${s.slice(0, n - 1).trimEnd()}...` : s;
}

export function argsToText(args: unknown): string {
  if (args === null || args === undefined) return "";
  if (typeof args === "string") return args;
  if (typeof args === "object") {
    const entries = Object.entries(args as Record<string, unknown>);
    if (entries.length === 0) return "";
    return entries
      .map(([k, v]) => `${k}=${typeof v === "string" ? JSON.stringify(v) : JSON.stringify(v)}`)
      .join(", ");
  }
  return String(args);
}
