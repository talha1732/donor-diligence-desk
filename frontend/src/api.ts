import type { DiligenceRequest, DiligenceResult, Health, OrgSearchResult, RunEvent, RunSummary } from "./types";
import { MOCK_HEALTH, MOCK_ORGS, MOCK_RUN_ID, MOCK_RUNS, SAMPLE_EVENTS, SAMPLE_RESULT } from "./mock/sampleEvents";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function errorMessage(res: Response, path = ""): Promise<string> {
  if (res.status === 429) return "Too many runs from this computer in the last minute. Wait a minute and try again.";
  try {
    const body = await res.json();
    const detail = body?.detail ?? body?.message ?? body?.error;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) {
      return detail.map((d: { msg: string; loc?: unknown[] }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
    }
  } catch {
    /* body was not JSON */
  }
  if (res.status === 404) return path ? `The server has no ${path.split("?")[0]} route (HTTP 404).` : "Not found (HTTP 404).";
  if (res.status >= 500) return `The server had a problem (HTTP ${res.status}).`;
  return `Request failed (HTTP ${res.status}).`;
}

async function getJSON<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError("Cannot reach the app server. Is `python backend/run.py` running?", 0);
  }
  if (!res.ok) throw new ApiError(await errorMessage(res, path), res.status);
  return (await res.json()) as T;
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Parses one SSE frame ("event: x\ndata: {...}") into a RunEvent. */
function parseFrame(frame: string): RunEvent | null {
  let eventType = "";
  const data: string[] = [];
  for (const raw of frame.split(/\r?\n/)) {
    if (!raw || raw.startsWith(":")) continue;
    const idx = raw.indexOf(":");
    const field = idx === -1 ? raw : raw.slice(0, idx);
    let value = idx === -1 ? "" : raw.slice(idx + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") eventType = value;
    else if (field === "data") data.push(value);
  }
  if (data.length === 0) return null;
  try {
    const parsed = JSON.parse(data.join("\n"));
    if (parsed && typeof parsed === "object" && "data" in parsed && ("type" in parsed || eventType)) {
      return { type: parsed.type ?? eventType, ts: parsed.ts ?? new Date().toISOString(), data: parsed.data } as RunEvent;
    }
    // Tolerate a bare payload with the type only in the `event:` line.
    if (eventType) return { type: eventType, ts: new Date().toISOString(), data: parsed } as RunEvent;
  } catch {
    /* ignore malformed frame */
  }
  return null;
}

export interface Api {
  mock: boolean;
  health(): Promise<Health>;
  featured(): Promise<OrgSearchResult[]>;
  search(q: string, state: string): Promise<OrgSearchResult[]>;
  runs(): Promise<RunSummary[]>;
  run(runId: string): Promise<DiligenceResult>;
  runEvents(runId: string): Promise<RunEvent[] | null>;
  stream(req: DiligenceRequest, onEvent: (e: RunEvent) => void, signal: AbortSignal): Promise<void>;
}

export const liveApi: Api = {
  mock: false,
  health: () => getJSON<Health>("/api/health"),
  featured: async () => (await getJSON<{ results: OrgSearchResult[] }>("/api/featured")).results ?? [],
  search: async (q, state) => {
    const params = new URLSearchParams({ q });
    if (state) params.set("state", state);
    return (await getJSON<{ results: OrgSearchResult[] }>(`/api/search?${params}`)).results ?? [];
  },
  runs: async () => (await getJSON<{ runs: RunSummary[] }>("/api/runs")).runs ?? [],
  run: (runId) => getJSON<DiligenceResult>(`/api/runs/${encodeURIComponent(runId)}`),
  runEvents: async (runId) => {
    try {
      return (await getJSON<{ events: RunEvent[] }>(`/api/runs/${encodeURIComponent(runId)}/events`)).events ?? null;
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  },
  stream: async (req, onEvent, signal) => {
    let res: Response;
    try {
      res = await fetch("/api/diligence/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify(req),
        signal,
      });
    } catch (e) {
      if (signal.aborted) return;
      throw new ApiError("Cannot reach the app server. Is `python backend/run.py` running?", 0);
    }
    if (!res.ok || !res.body) throw new ApiError(await errorMessage(res, "/api/diligence/stream"), res.status);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() ?? "";
      for (const f of frames) {
        const ev = parseFrame(f);
        if (ev) onEvent(ev);
      }
    }
    const tail = parseFrame(buffer);
    if (tail) onEvent(tail);
  },
};

export const mockApi: Api = {
  mock: true,
  health: async () => MOCK_HEALTH,
  featured: async () => MOCK_ORGS,
  search: async (q, state) => {
    await delay(250);
    const needle = q.trim().toLowerCase().replace(/-/g, "");
    return MOCK_ORGS.filter(
      (o) =>
        (!needle || o.name.toLowerCase().includes(needle) || o.ein.includes(needle)) &&
        (!state || (o.state ?? "").toUpperCase() === state.toUpperCase()),
    );
  },
  runs: async () => MOCK_RUNS,
  run: async (runId) => {
    if (runId !== MOCK_RUN_ID) throw new ApiError("That run is not in the bundled sample data.", 404);
    return SAMPLE_RESULT;
  },
  runEvents: async (runId) => (runId === MOCK_RUN_ID ? SAMPLE_EVENTS : null),
  stream: async (_req, onEvent, signal) => {
    // Mock streaming is handled by the replay player; this path is only a fallback.
    for (const e of SAMPLE_EVENTS) {
      if (signal.aborted) return;
      onEvent(e);
    }
  },
};
