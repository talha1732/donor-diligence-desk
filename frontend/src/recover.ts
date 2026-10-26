import type { Api } from "./api";
import type { DiligenceResult, RunEvent } from "./types";

// Recovery for live runs whose stream goes quiet or closes before the final event. The server saves
// runs/<run_id>.json before it sends `final`, so a finished run can always be loaded from disk instead.

/** Silence on an open stream before the app starts checking whether the run was saved. */
export const STALL_MS = 20_000;
export const POLL_MS = 5_000;
/** The server's run timeout; after this long the run has been saved or never will be. */
export const RUN_TIMEOUT_MS = 240_000;

export interface SavedRun {
  result: DiligenceResult;
  events: RunEvent[] | null;
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const t = window.setTimeout(done, ms);
    function done() {
      window.clearTimeout(t);
      signal.removeEventListener("abort", done);
      resolve();
    }
    signal.addEventListener("abort", done);
  });
}

/**
 * Polls every POLL_MS until the run is saved, `keepGoing` turns false, or the run timeout passes.
 * The check uses the run list, which answers 200 even before the run exists, so normal pauses between
 * events do not fill the console with 404s. The list is the audit trail, appended right after the run
 * file; in case that append failed, a closed stream (`direct`) also asks for the run itself every 30 s.
 */
export async function pollSavedRun(
  api: Api,
  runId: string,
  signal: AbortSignal,
  opts: { keepGoing: () => boolean; direct: () => boolean },
): Promise<SavedRun | null> {
  const deadline = Date.now() + RUN_TIMEOUT_MS;
  for (let attempt = 0; !signal.aborted && opts.keepGoing() && Date.now() < deadline; attempt++) {
    try {
      const listed = (await api.runs()).some((r) => r.run_id === runId);
      if ((listed || (opts.direct() && attempt % 6 === 5)) && !signal.aborted && opts.keepGoing()) {
        const result = await api.run(runId);
        const events = await api.runEvents(runId).catch(() => null);
        return { result, events };
      }
    } catch {
      // Not saved yet (404) or the server is busy: try again on the next tick.
    }
    await sleep(POLL_MS, signal);
  }
  return null;
}

/**
 * The events that rebuild the run screen as if the stream had delivered everything: the saved event log
 * (which already ends with `final` or `error`), or a closing event made from the saved result.
 * `reset` says whether the saved log replaces what the stream showed so far.
 */
export function recoveryEvents(saved: SavedRun): { reset: boolean; events: RunEvent[] } {
  const log = saved.events ?? [];
  if (log.some((e) => e.type === "final" || e.type === "error")) return { reset: true, events: log };
  const r = saved.result;
  const ts = new Date().toISOString();
  const end: RunEvent =
    r.status === "error"
      ? { type: "error", ts, data: { message: r.error ?? "The run stopped with an error.", partial: r } }
      : { type: "final", ts, data: r };
  return log.length ? { reset: true, events: [...log, end] } : { reset: false, events: [end] };
}
