import type { ToolCallData } from "./types";
import { argsToText } from "./format";

/** Plain-English wording for agent tool calls. The raw call stays available as technical detail. */

const FIELD_WORDS: Record<string, string> = {
  total_revenue: "total revenue",
  total_expenses: "total expenses",
  total_assets: "total assets",
  total_liabilities: "total liabilities",
  net_assets: "net assets",
  contributions: "contributions and grants",
  program_service_revenue: "program service revenue",
  investment_income: "investment income",
  officer_compensation: "officer pay",
  other_salaries: "other salaries",
  payroll_tax: "payroll tax",
  professional_fundraising_fees: "professional fundraising fees",
  fundraising_event_gross: "fundraising event income",
  fundraising_event_direct_expenses: "fundraising event costs",
};

const METRIC_WORDS: Record<string, string> = {
  total_revenue_latest: "latest revenue",
  total_expenses_latest: "latest expenses",
  surplus_margin: "surplus margin",
  avg_surplus_margin_3y: "3-year average surplus margin",
  net_assets_months: "reserves in months of expenses",
  liabilities_to_assets: "liabilities to assets",
  revenue_cagr_3y: "revenue growth per year",
  expense_cagr_3y: "expense growth per year",
  revenue_volatility_cv: "revenue volatility",
  contributions_share: "share of revenue from contributions",
  revenue_concentration_hhi: "revenue concentration",
  officer_comp_share: "officer pay as a share of expenses",
  staff_cost_share: "staff costs as a share of expenses",
  pro_fundraising_fee_share: "fundraising fees as a share of contributions",
  filing_recency_years: "years since the latest filing",
  years_of_filings: "years of filings",
  program_expense_share: "program-spending share",
};

function words(key: string, table: Record<string, string>): string {
  return table[key] ?? key.replace(/_/g, " ");
}

function arg(t: ToolCallData, name: string): string {
  const a = t.args;
  if (a && typeof a === "object" && name in (a as Record<string, unknown>)) {
    return String((a as Record<string, unknown>)[name] ?? "");
  }
  return "";
}

function shortUrl(url: string): string {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, "");
    if (host === "127.0.0.1" || host === "localhost") return `demo site ${u.pathname.replace(/^\/demo\//, "")}`;
    const path = u.pathname === "/" ? "" : u.pathname.replace(/\/$/, "");
    return host + path;
  } catch {
    return url;
  }
}

function plainResult(t: ToolCallData): string {
  const r = (t.result_summary ?? "").trim();
  if (!r) return "";
  switch (t.tool) {
    case "compare_years": {
      const m = r.match(/=\s*([+-]?[\d.,]+%)/);
      return m ? m[1] : r;
    }
    case "read_page": {
      const m = r.match(/:\s*(\d+)\s*chars,\s*(\d+)\s*numbers?/);
      if (m) return `${Number(m[1]).toLocaleString("en-US")} characters of visible text, ${m[2]} figures noted`;
      if (/^fetch failed/i.test(r)) return `could not read it (${r.replace(/^fetch failed:\s*/i, "")})`;
      if (/limit/i.test(r)) return "skipped: page limit reached";
      return r;
    }
    case "get_evidence": {
      const m = r.match(/^(\w+):\s*(.*)$/);
      return m ? m[2] : r;
    }
    default:
      return r;
  }
}

export function describeTool(t: ToolCallData): { text: string; result: string; raw: string } {
  const raw = `${t.tool}(${argsToText(t.args)})`;
  let text: string;
  switch (t.tool) {
    case "get_field_history":
      text = `Looked up ${words(arg(t, "field"), FIELD_WORDS)} across recent filings`;
      break;
    case "get_metric":
      text = `Checked the ${words(arg(t, "key"), METRIC_WORDS)}`;
      break;
    case "compare_years":
      text = `Compared ${words(arg(t, "field"), FIELD_WORDS)}, ${arg(t, "year_a")} to ${arg(t, "year_b")}`;
      break;
    case "search_web": {
      const q = arg(t, "query").replace(/\bsite:(\S+)/g, "").replace(/\s+/g, " ").trim();
      const site = arg(t, "query").match(/\bsite:(\S+)/);
      text = `Searched the web${site ? ` (${site[1]})` : ""} for "${q}"`;
      break;
    }
    case "read_page":
      text = `Read ${shortUrl(arg(t, "url"))}`;
      break;
    case "get_evidence": {
      const id = arg(t, "evidence_id");
      const kind = id.startsWith("CALC-") ? "a calculation" : id.startsWith("WEB-") ? "a website excerpt" : id.startsWith("PP-") ? "an IRS filing field" : "a source";
      text = `Re-checked ${kind} in the evidence ledger`;
      break;
    }
    default:
      text = t.tool.replace(/_/g, " ");
  }
  return { text, result: plainResult(t), raw };
}

const HIDDEN_REASON_WORDS: Record<string, string> = {
  "html-comment": "code comments",
  "display:none": "hidden blocks",
  "visibility:hidden": "hidden blocks",
  "opacity:0": "invisible text",
  "font-size:0": "zero-size text",
  "tiny-font": "tiny text",
  "white-on-white": "text in the background colour",
  offscreen: "text placed off screen",
  "aria-hidden": "text hidden from screen readers",
  "svg-text": "text inside graphics",
  hidden: "hidden blocks",
  meta: "page metadata",
};

/** Turns "Removed 32 hidden text segment(s) from URL (font-size:0, html-comment)" into plain words. */
export function plainSecurityDetail(detail: string): string {
  return detail
    .replace(/(\d+) hidden text segment\(s\)/, (_m, n) => `${n} piece${n === "1" ? "" : "s"} of text that visitors cannot see`)
    .replace(/\(([^()]*(?:html-comment|display:none|font-size:0|white-on-white|opacity:0|aria-hidden|offscreen|svg-text|tiny-font)[^()]*)\)/, (_m, list: string) => {
      const parts = Array.from(new Set(list.split(",").map((p) => p.trim()).map((p) => HIDDEN_REASON_WORDS[p] ?? p)));
      return `(${parts.join(", ")})`;
    });
}
