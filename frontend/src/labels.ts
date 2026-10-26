import type { Band, Dimension, EvidenceKind, SecurityEvent, SecurityKind, StageName } from "./types";

export const BAND_LABELS: Record<Band, string> = {
  strong_fit: "Strong fit",
  fit_with_questions: "Fit with questions",
  weak_fit: "Weak fit",
  insufficient_data: "Insufficient data",
};

export const BAND_HELP: Record<Band, string> = {
  strong_fit: "Overall score of 70 or more",
  fit_with_questions: "Overall score from 50 to under 70",
  weak_fit: "Overall score under 50",
  insufficient_data: "Two or more dimensions could not be scored",
};

export const STAGE_LABELS: Record<StageName, string> = {
  intake: "Intake",
  research: "Research",
  verify: "Verify",
  audit: "Audit",
  scoring: "Scoring",
  memo: "Memo",
};

export const STAGE_HELP: Record<StageName, string> = {
  intake: "Load IRS filings, compute ratios",
  research: "Analysts read filings and websites",
  verify: "Check every number against sources",
  audit: "Red-team review of the findings",
  scoring: "Apply the scoring rubric",
  memo: "Write the giving memo",
};

export const DIMENSION_HELP: Record<Dimension, string> = {
  financial_health: "Surplus or deficit, reserves, and debt load",
  revenue_resilience: "How diversified, steady, and growing revenue is",
  cost_discipline: "Officer pay, fundraising fees, and cost growth",
  transparency: "Recent filings, published results and financials",
  impact_evidence: "How strong the evidence is that programs work",
};

export const SECURITY_TITLES: Record<SecurityKind, string> = {
  hidden_text_removed: "Hidden text removed from website",
  injection_detected: "Instruction aimed at AI blocked",
  input_blocked: "Donor note blocked by screening",
  url_blocked: "Website address blocked",
  budget_stop: "Run stopped at its spending cap",
  daily_budget_stop: "Daily spending cap reached",
  rate_limited: "Too many runs in a minute",
  tool_limit: "Agent reached its tool-call limit",
  unverified_claim: "Unverified claim removed from memo",
};

export const SEVERITY_LABELS: Record<SecurityEvent["severity"], string> = {
  info: "Info",
  warning: "Warning",
  blocked: "Blocked",
};

export const EVIDENCE_KIND_LABELS: Record<EvidenceKind, string> = {
  irs_field: "IRS filing",
  calculation: "Calculation",
  web_excerpt: "Website",
  user_input: "Donor input",
};

export const EVIDENCE_KIND_SHORT: Record<EvidenceKind, string> = {
  irs_field: "IRS",
  calculation: "CALC",
  web_excerpt: "WEB",
  user_input: "YOU",
};

export function evidenceKindFromId(id: string): EvidenceKind {
  if (id.startsWith("PP-")) return "irs_field";
  if (id.startsWith("CALC-")) return "calculation";
  if (id.startsWith("WEB-")) return "web_excerpt";
  return "user_input";
}

export type AgentRole = "financial" | "impact" | "auditor" | "memo" | "other";

export function agentRole(agentKey: string): AgentRole {
  const prefix = agentKey.split(":")[0];
  if (prefix === "financial" || prefix === "impact" || prefix === "auditor" || prefix === "memo") return prefix;
  return "other";
}

export const ROLE_TITLES: Record<AgentRole, string> = {
  financial: "Financial Analyst",
  impact: "Impact Researcher",
  auditor: "Red-Team Auditor",
  memo: "Memo Writer",
  other: "Agent",
};

export const ROLE_DUTY: Record<AgentRole, string> = {
  financial: "Reads three to five years of Form 990 data and the computed ratios",
  impact: "Reads the charity's own website and looks for evidence of results",
  auditor: "Challenges every finding against the evidence ledger",
  memo: "Writes the memo from verified findings only",
  other: "",
};

export const TOOL_LABELS: Record<string, string> = {
  get_field_history: "IRS field history",
  get_metric: "Computed metric",
  compare_years: "Compare two years",
  search_web: "Web search",
  read_page: "Read web page",
  get_evidence: "Look up evidence",
};
