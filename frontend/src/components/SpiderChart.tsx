import type { DimensionScore } from "../types";
import { DIMENSIONS, DIMENSION_LABELS } from "../types";

interface Props {
  dimensions: DimensionScore[];
  title: string;
}

const W = 380;
const H = 318;
const CX = W / 2;
const CY = 166;
const R = 100;
const RINGS = [25, 50, 75, 100];
const N = DIMENSIONS.length;

const angle = (i: number) => -Math.PI / 2 + (2 * Math.PI * i) / N;
const pt = (i: number, v: number) => [CX + (R * v * Math.cos(angle(i))) / 100, CY + (R * v * Math.sin(angle(i))) / 100] as const;
const ringPath = (v: number) =>
  DIMENSIONS.map((_, i) => pt(i, v))
    .map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ") + " Z";

/** Scores in DIMENSIONS order, clamped to 0-100; null where the dimension could not be scored. */
function scoreValues(dimensions: DimensionScore[]): (number | null)[] {
  const byDim = new Map(dimensions.map((d) => [d.dimension, d]));
  return DIMENSIONS.map((d) => {
    const s = byDim.get(d)?.score;
    return s === null || s === undefined ? null : Math.max(0, Math.min(100, s));
  });
}

/**
 * Shape of one charity: a wedge and an edge only between neighbouring axes that both have a score,
 * so a missing dimension shows as a gap instead of a dip to zero.
 */
function shape(values: (number | null)[]) {
  const wedges: string[] = [];
  const edges: [number, number][] = [];
  for (let i = 0; i < N; i++) {
    const j = (i + 1) % N;
    const a = values[i];
    const b = values[j];
    if (a !== null && b !== null) {
      const [x1, y1] = pt(i, a);
      const [x2, y2] = pt(j, b);
      wedges.push(`M${CX},${CY} L${x1.toFixed(1)},${y1.toFixed(1)} L${x2.toFixed(1)},${y2.toFixed(1)} Z`);
      edges.push([i, j]);
    }
  }
  const scored = values.filter((v) => v !== null).length;
  return { wedges, edges, scored };
}

function Grid({ values }: { values?: (number | null)[] }) {
  return (
    <>
      {RINGS.map((r) => (
        <path key={r} d={ringPath(r)} className={r === 100 ? "ring ring-outer" : "ring"} />
      ))}
      {DIMENSIONS.map((d, i) => {
        const [x, y] = pt(i, 100);
        return <line key={d} x1={CX} y1={CY} x2={x} y2={y} className={values && values[i] === null ? "axis axis-missing" : "axis"} />;
      })}
      {RINGS.map((r) => (
        <text key={`l${r}`} x={CX - 5} y={CY - (R * r) / 100 + 11} textAnchor="end" className="ring-label">
          {r}
        </text>
      ))}
    </>
  );
}

/** Axis label lines: the dimension name split into words, plus an optional value line. */
function AxisLabels({ valueLine }: { valueLine?: (i: number) => { text: string; missing: boolean } }) {
  return (
    <>
      {DIMENSIONS.map((d, i) => {
        const a = angle(i);
        const lx = CX + (R + 16) * Math.cos(a);
        const ly = CY + (R + 16) * Math.sin(a);
        const cos = Math.cos(a);
        const sin = Math.sin(a);
        const anchor = cos > 0.3 ? "start" : cos < -0.3 ? "end" : "middle";
        const words = DIMENSION_LABELS[d].split(" ");
        const extra = valueLine?.(i);
        const lines = extra ? [...words, extra.text] : words;
        const lineH = 14;
        const startY = sin < -0.5 ? ly - (lines.length - 1) * lineH - 2 : sin > 0.5 ? ly + 10 : ly - ((lines.length - 1) * lineH) / 2 + 4;
        return (
          <text key={`t${d}`} x={lx} y={startY} textAnchor={anchor} className="axis-label">
            {lines.map((ln, k) => (
              <tspan
                key={k}
                x={lx}
                dy={k === 0 ? 0 : lineH}
                className={extra && k === lines.length - 1 ? (extra.missing ? "axis-nodata" : "axis-value") : undefined}
              >
                {ln}
              </tspan>
            ))}
          </text>
        );
      })}
    </>
  );
}

/** Radar chart on a fixed 0-100 scale. Missing dimensions are drawn as gaps, never as zero. */
export function SpiderChart({ dimensions, title }: Props) {
  const values = scoreValues(dimensions);
  const { wedges, edges, scored } = shape(values);
  const summary = DIMENSIONS.map((d, i) => `${DIMENSION_LABELS[d]} ${values[i] === null ? "no data" : Math.round(values[i]!)}`).join(", ");

  return (
    <svg className="spider" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}: ${summary}`}>
      <title>{`${title}: ${summary}`}</title>
      <Grid values={values} />
      {wedges.map((w, k) => (
        <path key={k} d={w} className="wedge" />
      ))}
      {edges.map(([i, j]) => {
        const [x1, y1] = pt(i, values[i]!);
        const [x2, y2] = pt(j, values[j]!);
        return <line key={`e${i}`} x1={x1} y1={y1} x2={x2} y2={y2} className="edge" />;
      })}
      {scored === 1 &&
        values.map((v, i) => {
          if (v === null) return null;
          const [x, y] = pt(i, v);
          return <line key={`s${i}`} x1={CX} y1={CY} x2={x} y2={y} className="edge" />;
        })}
      {values.map((v, i) => {
        if (v === null) return null;
        const [x, y] = pt(i, v);
        return (
          <circle key={`p${i}`} cx={x} cy={y} r={4.5} className="point">
            <title>{`${DIMENSION_LABELS[DIMENSIONS[i]]}: ${Math.round(v)} of 100`}</title>
          </circle>
        );
      })}
      <AxisLabels valueLine={(i) => ({ text: values[i] === null ? "no data" : String(Math.round(values[i]!)), missing: values[i] === null })} />
    </svg>
  );
}

export interface RadarSeries {
  key: string;
  name: string;
  dimensions: DimensionScore[];
}

/** Marker shape per series slot, so identity never depends on colour alone. */
export function SeriesMarker({ slot, x, y, size = 4.5 }: { slot: number; x: number; y: number; size?: number }) {
  if (slot === 1) return <rect x={x - size} y={y - size} width={size * 2} height={size * 2} rx={1.2} />;
  if (slot === 2) return <path d={`M${x},${y - size * 1.3} L${x + size * 1.3},${y} L${x},${y + size * 1.3} L${x - size * 1.3},${y} Z`} />;
  return <circle cx={x} cy={y} r={size} />;
}

/** Every charity on one radar, same 0-100 scale and the same gap rule as the per-charity charts. */
export function ComparisonRadar({ series, title }: { series: RadarSeries[]; title: string }) {
  const all = series.map((s) => ({ ...s, values: scoreValues(s.dimensions) }));
  const missingEverywhere = DIMENSIONS.map((_, i) => all.every((s) => s.values[i] === null));
  const summary = all
    .map((s) => `${s.name}: ${DIMENSIONS.map((d, i) => `${DIMENSION_LABELS[d]} ${s.values[i] === null ? "no data" : Math.round(s.values[i]!)}`).join(", ")}`)
    .join(". ");

  return (
    <svg className="spider spider-compare" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}. ${summary}`}>
      <title>{`${title}. ${summary}`}</title>
      <Grid values={missingEverywhere.map((m) => (m ? null : 0))} />
      {all.map((s, slot) => {
        const { wedges } = shape(s.values);
        return (
          <g key={`f${s.key}`} className={`series series-${slot}`}>
            {wedges.map((w, k) => (
              <path key={k} d={w} className="wedge" />
            ))}
          </g>
        );
      })}
      {all.map((s, slot) => {
        const { edges, scored } = shape(s.values);
        return (
          <g key={`l${s.key}`} className={`series series-${slot}`}>
            {edges.map(([i, j]) => {
              const [x1, y1] = pt(i, s.values[i]!);
              const [x2, y2] = pt(j, s.values[j]!);
              return <line key={`e${i}`} x1={x1} y1={y1} x2={x2} y2={y2} className="edge" />;
            })}
            {scored === 1 &&
              s.values.map((v, i) => {
                if (v === null) return null;
                const [x, y] = pt(i, v);
                return <line key={`s${i}`} x1={CX} y1={CY} x2={x} y2={y} className="edge" />;
              })}
          </g>
        );
      })}
      {all.map((s, slot) => (
        <g key={`p${s.key}`} className={`series series-${slot} series-points`}>
          {s.values.map((v, i) => {
            if (v === null) return null;
            const [x, y] = pt(i, v);
            return (
              <g key={i} className="point">
                <title>{`${s.name}, ${DIMENSION_LABELS[DIMENSIONS[i]]}: ${Math.round(v)} of 100`}</title>
                <SeriesMarker slot={slot} x={x} y={y} size={slot === 2 ? 3.6 : 4} />
              </g>
            );
          })}
        </g>
      ))}
      <AxisLabels />
    </svg>
  );
}
