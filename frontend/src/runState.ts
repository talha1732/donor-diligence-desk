import type {
  AgentUsage,
  DiligenceResult,
  RunEvent,
  RunUsage,
  SecurityEvent,
  StageName,
  StepToolCall,
  ToolCallData,
  Weights,
} from "./types";
import { STAGES } from "./types";
import { agentRole, type AgentRole } from "./labels";

export type AgentStatus = "waiting" | "running" | "done" | "error" | "stopped";
export type StageStatus = "pending" | "active" | "done" | "stopped";

export interface AgentView {
  key: string;
  role: AgentRole;
  ein: string | null;
  label: string | null;
  status: AgentStatus;
  step: number;
  activity: string;
  lastText: string | null;
  toolCalls: (ToolCallData & { ts: string })[];
  usage: AgentUsage | null;
  summary: string | null;
  startedTs: string | null;
  endedTs: string | null;
}

export interface RunState {
  status: "idle" | "connecting" | "running" | "done" | "error";
  runId: string | null;
  model: string | null;
  budgetUsd: number | null;
  defensesOn: boolean;
  charities: { ein: string; name: string; is_demo: boolean }[];
  weights: Weights | null;
  stages: Record<StageName, StageStatus>;
  agents: Record<string, AgentView>;
  agentOrder: string[];
  toolLog: (ToolCallData & { ts: string })[];
  evidenceIds: string[];
  security: (SecurityEvent & { ts: string })[];
  usage: RunUsage | null;
  result: DiligenceResult | null;
  error: string | null;
  firstTs: string | null;
  lastTs: string | null;
  eventCount: number;
}

const emptyStages = (): Record<StageName, StageStatus> =>
  Object.fromEntries(STAGES.map((s) => [s, "pending"])) as Record<StageName, StageStatus>;

export const initialRunState: RunState = {
  status: "idle",
  runId: null,
  model: null,
  budgetUsd: null,
  defensesOn: true,
  charities: [],
  weights: null,
  stages: emptyStages(),
  agents: {},
  agentOrder: [],
  toolLog: [],
  evidenceIds: [],
  security: [],
  usage: null,
  result: null,
  error: null,
  firstTs: null,
  lastTs: null,
  eventCount: 0,
};

export type RunAction =
  | { type: "reset" }
  | { type: "connecting" }
  | { type: "event"; event: RunEvent }
  | { type: "batch"; events: RunEvent[] }
  | { type: "fail"; message: string }
  | { type: "loadResult"; result: DiligenceResult };

function newAgent(key: string, ein: string | null, label: string | null): AgentView {
  return {
    key,
    role: agentRole(key),
    ein,
    label,
    status: "waiting",
    step: 0,
    activity: "Waiting to start",
    lastText: null,
    toolCalls: [],
    usage: null,
    summary: null,
    startedTs: null,
    endedTs: null,
  };
}

function toolName(t: StepToolCall): string {
  if (typeof t === "string") return t;
  return t.tool ?? t.tool_name ?? t.name ?? "tool";
}

function ensureAgent(s: RunState, key: string, ein?: string | null, label?: string | null): RunState {
  if (s.agents[key]) return s;
  return {
    ...s,
    agents: { ...s.agents, [key]: newAgent(key, ein ?? null, label ?? null) },
    agentOrder: [...s.agentOrder, key],
  };
}

function patchAgent(s: RunState, key: string, patch: Partial<AgentView>, ein?: string | null): RunState {
  const s2 = ensureAgent(s, key, ein);
  return { ...s2, agents: { ...s2.agents, [key]: { ...s2.agents[key], ...patch } } };
}

function applyResult(s: RunState, r: DiligenceResult): RunState {
  let next: RunState = {
    ...s,
    runId: r.run_id,
    result: r,
    usage: r.usage ?? s.usage,
    model: s.model ?? r.usage?.model ?? null,
    budgetUsd: s.budgetUsd ?? r.usage?.budget_usd ?? null,
    defensesOn: r.defenses_on,
  };
  if (next.security.length === 0 && r.security_events.length > 0) {
    next.security = r.security_events.map((e) => ({ ...e, ts: r.created_at }));
  }
  if (next.charities.length === 0) {
    next.charities = r.orgs.map((o) => ({ ein: o.ein, name: o.name, is_demo: o.is_demo }));
  }
  if (next.evidenceIds.length === 0) next.evidenceIds = Object.keys(r.evidence);
  // Fill agent cards from usage when no events were seen (e.g. a saved run without an event log).
  for (const u of r.usage?.agents ?? []) {
    const ein = u.agent.includes(":") ? u.agent.split(":")[1] : null;
    next = ensureAgent(next, u.agent, ein);
    const a = next.agents[u.agent];
    const report = r.reports.find((rep) => rep.agent === u.agent);
    const status: AgentStatus =
      a.status === "waiting" || a.status === "running"
        ? report?.status === "error"
          ? "error"
          : report?.status === "stopped"
            ? "stopped"
            : "done"
        : a.status;
    next = patchAgent(next, u.agent, {
      usage: u,
      status,
      activity: status === "done" ? "Finished" : a.activity,
      summary: a.summary ?? report?.summary ?? report?.error ?? null,
    });
  }
  return next;
}

/** Once a run ends early, nothing is still working: freeze in-flight agents and stages. */
function freeze(s: RunState): RunState {
  const agents: Record<string, AgentView> = {};
  for (const [k, a] of Object.entries(s.agents)) {
    agents[k] = a.status === "running" ? { ...a, status: "stopped", activity: "Stopped when the run ended" } : a;
  }
  const stages = { ...s.stages };
  for (const st of STAGES) if (stages[st] === "active") stages[st] = "stopped";
  return { ...s, agents, stages };
}

export function reduceEvent(s: RunState, e: RunEvent): RunState {
  const base: RunState = {
    ...s,
    eventCount: s.eventCount + 1,
    firstTs: s.firstTs ?? e.ts,
    lastTs: e.ts,
    status: s.status === "idle" || s.status === "connecting" ? "running" : s.status,
  };
  switch (e.type) {
    case "run_started": {
      const d = e.data;
      let next: RunState = {
        ...base,
        runId: d.run_id,
        model: d.model,
        budgetUsd: d.budget_usd,
        defensesOn: d.defenses_on,
        charities: d.charities,
        weights: d.weights,
      };
      // Pre-create the cards so the user sees the whole team before it starts working.
      for (const c of d.charities) {
        next = ensureAgent(next, `financial:${c.ein}`, c.ein);
        next = ensureAgent(next, `impact:${c.ein}`, c.ein);
      }
      next = ensureAgent(next, "auditor", null);
      next = ensureAgent(next, "memo", null);
      return next;
    }
    case "stage": {
      const st: StageStatus = e.data.status === "done" ? "done" : "active";
      return { ...base, stages: { ...base.stages, [e.data.stage]: st } };
    }
    case "agent_started": {
      const d = e.data;
      const next = ensureAgent(base, d.agent, d.ein, d.label);
      return patchAgent(next, d.agent, {
        status: "running",
        activity: "Starting",
        label: d.label ?? next.agents[d.agent].label,
        ein: d.ein ?? next.agents[d.agent].ein,
        startedTs: e.ts,
      });
    }
    case "agent_step": {
      const d = e.data;
      const cur = ensureAgent(base, d.agent, d.ein).agents[d.agent];
      let activity = cur.activity;
      if (d.kind === "model_request") activity = `Thinking (model request ${d.step})`;
      else if (d.kind === "model_response") {
        const tools = (d.tool_calls ?? []).map(toolName);
        activity = tools.length ? `Calling ${tools.join(", ")}` : "Writing its findings";
      } else if (d.kind === "end") activity = "Finished";
      return patchAgent(
        base,
        d.agent,
        {
          step: Math.max(cur.step, d.step ?? 0),
          activity,
          lastText: d.text ? d.text : cur.lastText,
          status: cur.status === "waiting" ? "running" : cur.status,
          startedTs: cur.startedTs ?? e.ts,
        },
        d.ein,
      );
    }
    case "tool_call": {
      const d = { ...e.data, ts: e.ts };
      const cur = ensureAgent(base, d.agent, d.ein).agents[d.agent];
      const next = patchAgent(base, d.agent, { toolCalls: [...cur.toolCalls, d] }, d.ein);
      return { ...next, toolLog: [...next.toolLog, d] };
    }
    case "evidence_added": {
      const seen = new Set(base.evidenceIds);
      const add = (e.data.ids ?? []).filter((id) => !seen.has(id));
      return { ...base, evidenceIds: [...base.evidenceIds, ...add] };
    }
    case "security":
      return { ...base, security: [...base.security, { ...e.data, ts: e.ts }] };
    case "spend":
      return { ...base, usage: e.data };
    case "agent_done": {
      const d = e.data;
      const status: AgentStatus = d.status === "done" ? "done" : d.status === "stopped" ? "stopped" : "error";
      return patchAgent(
        base,
        d.agent,
        {
          status,
          activity: status === "done" ? "Finished" : status === "stopped" ? "Stopped" : "Stopped with an error",
          usage: d.usage ?? null,
          summary: d.summary ?? null,
          endedTs: e.ts,
        },
        d.ein,
      );
    }
    case "final": {
      const done = applyResult(base, e.data);
      const stages = { ...done.stages };
      if (e.data.status === "complete") for (const st of STAGES) stages[st] = "done";
      const finished = { ...done, stages, status: "done" as const };
      return e.data.status === "complete" ? finished : freeze(finished);
    }
    case "error": {
      let next: RunState = { ...base, status: "error", error: e.data.message || "The run stopped with an error." };
      if (e.data.partial) next = applyResult(next, e.data.partial);
      return freeze(next);
    }
    default:
      return base;
  }
}

export function runReducer(s: RunState, a: RunAction): RunState {
  switch (a.type) {
    case "reset":
      return initialRunState;
    case "connecting":
      return { ...initialRunState, status: "connecting" };
    case "event":
      return reduceEvent(s, a.event);
    case "batch":
      return a.events.reduce(reduceEvent, s);
    case "fail":
      return freeze({ ...s, status: "error", error: a.message });
    case "loadResult": {
      const next = applyResult(s, a.result);
      const stages = { ...next.stages };
      for (const st of STAGES) stages[st] = "done";
      return {
        ...next,
        stages,
        status: a.result.status === "error" ? "error" : "done",
        error: a.result.error ?? next.error,
        firstTs: next.firstTs ?? a.result.created_at,
        lastTs: next.lastTs ?? a.result.created_at,
      };
    }
  }
}

export function elapsedSeconds(s: RunState): number {
  if (!s.firstTs || !s.lastTs) return 0;
  return Math.max(0, (Date.parse(s.lastTs) - Date.parse(s.firstTs)) / 1000);
}
