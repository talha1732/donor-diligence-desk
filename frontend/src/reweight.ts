import type { Band, CharityScorecard, Weights } from "./types";
import { DIMENSIONS } from "./types";

// Client-side mirror of backend/app/tools/scoring.py (_weights, the overall in score_charity, band_for).
// Dimension scores never depend on weights, so only the weighted mean and the band are recomputed here.

export const BAND_STRONG = 70;
export const BAND_FIT = 50;

export interface Rescored {
  overall: number | null;
  band: Band;
}

export function sameWeights(a: Weights, b: Weights): boolean {
  return DIMENSIONS.every((d) => Number(a[d]) === Number(b[d]));
}

/** scoring._weights: all-zero weights mean equal weights. */
export function effectiveWeights(w: Weights): Weights {
  if (DIMENSIONS.every((d) => Number(w[d]) === 0)) {
    return { financial_health: 1, revenue_resilience: 1, cost_discipline: 1, transparency: 1, impact_evidence: 1 };
  }
  return { ...w };
}

/** Python 3.12 sum() over floats: the first item exactly, then Neumaier compensated summation. */
function pySum(xs: number[]): number {
  if (xs.length === 0) return 0;
  let s = xs[0];
  let c = 0;
  for (let i = 1; i < xs.length; i++) {
    const x = xs[i];
    const t = s + x;
    c += Math.abs(s) >= Math.abs(x) ? s - t + x : x - t + s;
    s = t;
  }
  return c && Number.isFinite(c) ? s + c : s;
}

/** Python round(x, 1): correctly rounded on the exact binary value, ties to even. */
function pyRound1(x: number): number {
  // An exact tie at one decimal only happens when x is k + 0.25 or k + 0.75 in binary.
  if (Number.isInteger(x * 4) && !Number.isInteger(x * 2)) {
    const lo = Math.floor(x * 10);
    return (lo % 2 === 0 ? lo : lo + 1) / 10;
  }
  return Number(x.toFixed(1));
}

/** scoring.band_for */
export function bandFor(overall: number | null, noneCount: number, hasFilings: boolean): Band {
  if (!hasFilings || noneCount >= 2 || overall === null) return "insufficient_data";
  if (overall >= BAND_STRONG) return "strong_fit";
  if (overall >= BAND_FIT) return "fit_with_questions";
  return "weak_fit";
}

/**
 * Overall and band for one scorecard under new weights. `hasFilings` is profile.filings being non-empty;
 * the saved result does not carry the filings list, so the caller infers it from the metrics.
 */
export function rescore(card: CharityScorecard, weights: Weights, hasFilings: boolean): Rescored {
  const w = effectiveWeights(weights);
  // Keep the backend's dimension order so the floating-point sums match.
  const scored = card.dimensions.filter((d) => d.score !== null && d.score !== undefined);
  const totalWeight = pySum(scored.map((d) => Number(w[d.dimension])));
  const overall = totalWeight > 0 ? pyRound1(pySum(scored.map((d) => (d.score as number) * Number(w[d.dimension]))) / totalWeight) : null;
  const noneCount = DIMENSIONS.length - scored.length;
  return { overall, band: bandFor(overall, noneCount, hasFilings) };
}

/**
 * Whether the charity had any Form 990 filings with data. years_of_data is len(profile.filings).
 * A saved band of insufficient_data that the dimensions and overall cannot explain also means no filings.
 */
export function inferHasFilings(card: CharityScorecard, yearsOfData: number | undefined): boolean {
  if (yearsOfData !== undefined && yearsOfData <= 0) return false;
  const noneCount = DIMENSIONS.length - card.dimensions.filter((d) => d.score !== null && d.score !== undefined).length;
  if (card.band === "insufficient_data" && noneCount < 2 && card.overall !== null && card.overall !== undefined) return false;
  return true;
}
