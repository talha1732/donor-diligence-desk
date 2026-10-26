// Mirrors backend/app/schemas.py (frozen contract). Keep field names identical.

export type Unit = "usd" | "ratio" | "months" | "years" | "count" | "text";

export type Dimension =
  | "financial_health"
  | "revenue_resilience"
  | "cost_discipline"
  | "transparency"
  | "impact_evidence";

export const DIMENSIONS: Dimension[] = [
  "financial_health",
  "revenue_resilience",
  "cost_discipline",
  "transparency",
  "impact_evidence",
];

export const DIMENSION_LABELS: Record<Dimension, string> = {
  financial_health: "Financial health",
  revenue_resilience: "Revenue resilience",
  cost_discipline: "Cost discipline",
  transparency: "Transparency",
  impact_evidence: "Impact evidence",
};

export type Band = "strong_fit" | "fit_with_questions" | "weak_fit" | "insufficient_data";

// ---------------------------------------------------------------- request

export interface Weights {
  financial_health: number;
  revenue_resilience: number;
  cost_discipline: number;
  transparency: number;
  impact_evidence: number;
}

export interface CharityInput {
  ein: string;
  website_url?: string | null;
}

export interface DiligenceRequest {
  charities: CharityInput[];
  weights: Weights;
  donor_note: string;
  budget_usd?: number | null;
  defenses_off?: boolean;
}

// ---------------------------------------------------------------- ProPublica data

export interface OrgSearchResult {
  ein: string;
  name: string;
  city?: string | null;
  state?: string | null;
  ntee_code?: string | null;
  subsection_code?: number | null;
  latest_revenue?: number | null;
  is_demo: boolean;
}

export interface FilingYear {
  tax_year: number;
  tax_period?: number | null;
  form_type?: string | null;
  pdf_url?: string | null;
  total_revenue?: number | null;
  total_expenses?: number | null;
  total_assets?: number | null;
  total_liabilities?: number | null;
  net_assets?: number | null;
  contributions?: number | null;
  program_service_revenue?: number | null;
  investment_income?: number | null;
  officer_compensation?: number | null;
  other_salaries?: number | null;
  payroll_tax?: number | null;
  professional_fundraising_fees?: number | null;
  fundraising_event_gross?: number | null;
  fundraising_event_direct_expenses?: number | null;
}

export interface OrgProfile {
  ein: string;
  name: string;
  city?: string | null;
  state?: string | null;
  ntee_code?: string | null;
  subsection_code?: number | null;
  ruling_date?: string | null;
  is_demo: boolean;
  website_url?: string | null;
  source_url: string;
  filings: FilingYear[];
  filings_without_data_years: number[];
  fetched_at: string;
  from_cache: boolean;
}

// ---------------------------------------------------------------- evidence ledger

export type EvidenceKind = "irs_field" | "calculation" | "web_excerpt" | "user_input";

export interface Evidence {
  id: string;
  kind: EvidenceKind;
  ein?: string | null;
  label: string;
  value?: number | null;
  unit: Unit;
  display: string;
  source_url?: string | null;
  excerpt?: string | null;
  inputs: string[];
  tax_year?: number | null;
}

export interface Metric {
  key: string;
  label: string;
  value?: number | null;
  unit: Unit;
  display?: string | null;
  evidence_id?: string | null;
  reason_missing?: string | null;
  tax_year?: number | null;
}

export interface FinancialMetrics {
  ein: string;
  latest_tax_year?: number | null;
  years_of_data: number;
  metrics: Record<string, Metric>;
}

// ---------------------------------------------------------------- web

export interface HiddenSegment {
  reason: string;
  text: string;
}

export interface InjectionFinding {
  pattern: string;
  snippet: string;
  location: "visible" | "hidden" | "user_input" | "search_snippet";
}

// ---------------------------------------------------------------- agent outputs

export type Stance = "strength" | "concern" | "neutral";

export interface Finding {
  id: string;
  ein?: string | null;
  agent: string;
  dimension: Dimension | "mission_fit" | "other";
  stance: Stance;
  text: string;
  evidence_ids: string[];
}

export interface ImpactAssessment {
  ein: string;
  website_url?: string | null;
  pages_read: string[];
  evidence_level: number;
  evidence_level_label: string;
  rationale: string;
  publishes_financials?: boolean | null;
  publishes_outcomes?: boolean | null;
  mission_fit_note: string;
  evidence_ids: string[];
}

export const IMPACT_EVIDENCE_LEVELS: Record<number, string> = {
  0: "No information found about results",
  1: "Stories or anecdotes only",
  2: "Reports outputs (people served, meals, etc.)",
  3: "Reports measured outcomes against goals",
  4: "Independent evaluation or rigorous study",
};

export interface SpecialistReport {
  agent: string;
  role: "financial" | "impact";
  ein: string;
  status: "done" | "error" | "stopped";
  summary: string;
  findings: Finding[];
  questions_for_charity: string[];
  could_not_verify: string[];
  impact?: ImpactAssessment | null;
  error?: string | null;
}

// ---------------------------------------------------------------- audit

export type ClaimStatus =
  | "verified"
  | "unverified_number"
  | "missing_evidence"
  | "unknown_evidence_id"
  | "no_numbers";

export interface ClaimCheck {
  finding_id: string;
  status: ClaimStatus;
  numbers_checked: string[];
  unmatched_numbers: string[];
  detail: string;
}

export interface VerificationReport {
  checks: ClaimCheck[];
  verified_count: number;
  flagged_count: number;
}

export interface AuditReport {
  verification: VerificationReport;
  auditor_notes: string[];
  removed_finding_ids: string[];
  added_questions: Record<string, string[]>;
}

// ---------------------------------------------------------------- scoring

export interface DimensionScore {
  dimension: Dimension;
  label: string;
  score?: number | null;
  weight: number;
  drivers: string[];
  explanation: string;
  missing_inputs: string[];
}

export interface CharityScorecard {
  ein: string;
  name: string;
  is_demo: boolean;
  dimensions: DimensionScore[];
  overall?: number | null;
  band: Band;
}

// ---------------------------------------------------------------- memo

export interface CharitySection {
  ein: string;
  name: string;
  is_demo: boolean;
  band: Band;
  overall?: number | null;
  one_line: string;
  strengths: Finding[];
  concerns: Finding[];
  questions_for_charity: string[];
  could_not_verify: string[];
}

export interface GivingMemo {
  headline: string;
  summary: string;
  recommendation: string;
  charities: CharitySection[];
  method_note: string;
  disclaimer: string;
  text_checks: ClaimCheck[];
}

// ---------------------------------------------------------------- usage, safety, result

export interface AgentUsage {
  agent: string;
  requests: number;
  input_tokens: number;
  cached_tokens: number;
  cache_write_tokens: number;
  output_tokens: number;
  tool_calls: number;
  cost_usd: number;
  seconds: number;
}

export interface RunUsage {
  model: string;
  agents: AgentUsage[];
  total: AgentUsage;
  budget_usd: number;
  stopped_by_budget: boolean;
}

export type SecurityKind =
  | "hidden_text_removed"
  | "injection_detected"
  | "input_blocked"
  | "url_blocked"
  | "budget_stop"
  | "daily_budget_stop"
  | "rate_limited"
  | "tool_limit"
  | "unverified_claim";

export interface SecurityEvent {
  kind: SecurityKind;
  severity: "info" | "warning" | "blocked";
  agent?: string | null;
  ein?: string | null;
  detail: string;
  snippet?: string | null;
}

export interface DiligenceResult {
  run_id: string;
  created_at: string;
  status: "complete" | "stopped_budget" | "error";
  error?: string | null;
  defenses_on: boolean;
  request: DiligenceRequest;
  orgs: OrgSearchResult[];
  metrics: FinancialMetrics[];
  reports: SpecialistReport[];
  audit?: AuditReport | null;
  scorecards: CharityScorecard[];
  memo?: GivingMemo | null;
  evidence: Record<string, Evidence>;
  security_events: SecurityEvent[];
  usage: RunUsage;
}

// ---------------------------------------------------------------- SSE events (contract section 8)

export type StageName = "intake" | "research" | "verify" | "audit" | "scoring" | "memo";
export const STAGES: StageName[] = ["intake", "research", "verify", "audit", "scoring", "memo"];

export interface RunStartedData {
  run_id: string;
  model: string;
  budget_usd: number;
  defenses_on: boolean;
  charities: { ein: string; name: string; is_demo: boolean }[];
  weights: Weights;
}

export interface StageData {
  stage: StageName;
  status: "started" | "done";
}

export interface AgentStartedData {
  agent: string;
  role: string;
  ein?: string | null;
  label?: string | null;
}

// tool_calls entries are not pinned by the contract; accept strings or objects.
export type StepToolCall = string | { tool?: string; tool_name?: string; name?: string; args?: unknown };

export interface AgentStepData {
  agent: string;
  ein?: string | null;
  step: number;
  kind: "model_request" | "model_response" | "end";
  text?: string | null;
  tool_calls?: StepToolCall[] | null;
  usage?: Partial<AgentUsage> | null;
}

export interface ToolCallData {
  agent: string;
  ein?: string | null;
  tool: string;
  args?: unknown;
  result_summary?: string | null;
  ms?: number | null;
}

export interface EvidenceAddedData {
  ids: string[];
  count: number;
}

export interface AgentDoneData {
  agent: string;
  ein?: string | null;
  status: string;
  usage?: AgentUsage | null;
  summary?: string | null;
}

export interface ErrorData {
  message: string;
  partial?: DiligenceResult | null;
}

export type RunEvent =
  | { type: "run_started"; ts: string; data: RunStartedData }
  | { type: "stage"; ts: string; data: StageData }
  | { type: "agent_started"; ts: string; data: AgentStartedData }
  | { type: "agent_step"; ts: string; data: AgentStepData }
  | { type: "tool_call"; ts: string; data: ToolCallData }
  | { type: "evidence_added"; ts: string; data: EvidenceAddedData }
  | { type: "security"; ts: string; data: SecurityEvent }
  | { type: "spend"; ts: string; data: RunUsage }
  | { type: "agent_done"; ts: string; data: AgentDoneData }
  | { type: "final"; ts: string; data: DiligenceResult }
  | { type: "error"; ts: string; data: ErrorData };

// ---------------------------------------------------------------- HTTP API (contract section 9)

export interface Health {
  ok: boolean;
  model: string;
  portkey_key_set: boolean;
  offline_mode: boolean;
  allow_defense_toggle: boolean;
  run_budget_usd: number;
  daily_budget_usd: number;
  daily_spent_usd: number;
}

// Compact audit record from GET /api/runs. Only run_id is assumed; everything else is optional.
export interface RunSummary {
  run_id: string;
  created_at?: string;
  status?: string;
  sample?: boolean;
  charities?: (string | { ein?: string; name?: string; band?: Band; overall?: number | null })[];
  names?: string[];
  orgs?: { ein?: string; name?: string }[];
  headline?: string;
  cost_usd?: number;
  total_cost_usd?: number;
  model?: string;
  defenses_on?: boolean;
  [key: string]: unknown;
}
