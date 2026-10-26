import type { RunEvent } from "./types";

export interface Player {
  skipToEnd: () => void;
  cancel: () => void;
}

/** Longest pause between two replayed events, so long agent waits do not stall the screen. */
const MAX_GAP_MS = 1400;

/**
 * Replays recorded run events with their original timing divided by `speed`.
 * speed <= 0 delivers everything at once.
 */
export function playEvents(
  events: RunEvent[],
  speed: number,
  onBatch: (events: RunEvent[]) => void,
  onFinish?: () => void,
): Player {
  let i = 0;
  let timer: number | undefined;
  let cancelled = false;

  const finish = () => {
    if (i < events.length) {
      onBatch(events.slice(i));
      i = events.length;
    }
    onFinish?.();
  };

  if (speed <= 0 || events.length === 0) {
    finish();
    return { skipToEnd: () => undefined, cancel: () => undefined };
  }

  const tick = () => {
    if (cancelled) return;
    // Deliver every event that shares this timestamp window together.
    const start = i;
    const t0 = Date.parse(events[i].ts);
    i += 1;
    while (i < events.length && (Date.parse(events[i].ts) - t0) / speed < 30) i += 1;
    onBatch(events.slice(start, i));
    if (i >= events.length) {
      onFinish?.();
      return;
    }
    const gap = (Date.parse(events[i].ts) - Date.parse(events[i - 1].ts)) / speed;
    timer = window.setTimeout(tick, Math.max(0, Math.min(MAX_GAP_MS, gap)));
  };
  timer = window.setTimeout(tick, 250);

  return {
    skipToEnd: () => {
      if (cancelled) return;
      cancelled = true;
      window.clearTimeout(timer);
      finish();
    },
    cancel: () => {
      cancelled = true;
      window.clearTimeout(timer);
    },
  };
}
