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

/** Radar chart on a fixed 0-100 scale. Missing dimensions are drawn as gaps, never as zero. */
export function SpiderChart({ dimensions, title }: Props) {
  const byDim = new Map(dimensions.map((d) => [d.dimension, d]));
  const n = DIMENSIONS.length;
  const angle = (i: number) => -Math.PI / 2 + (2 * Math.PI * i) / n;
  const pt = (i: number, v: number) => [CX + (R * v * Math.cos(angle(i))) / 100, CY + (R * v * Math.sin(angle(i))) / 100] as const;
  const values = DIMENSIONS.map((d) => {
    const s = byDim.get(d)?.score;
    return s === null || s === undefined ? null : Math.max(0, Math.min(100, s));
  });
  const ringPath = (v: number) =>
    DIMENSIONS.map((_, i) => pt(i, v))
      .map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`)
      .join(" ") + " Z";

  const wedges: string[] = [];
  const edges: [number, number][] = [];
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
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
  const summary = DIMENSIONS.map((d, i) => `${DIMENSION_LABELS[d]} ${values[i] === null ? "no data" : Math.round(values[i]!)}`).join(", ");

  return (
    <svg className="spider" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}: ${summary}`}>
      <title>{`${title}: ${summary}`}</title>
      {RINGS.map((r) => (
        <path key={r} d={ringPath(r)} className={r === 100 ? "ring ring-outer" : "ring"} />
      ))}
      {DIMENSIONS.map((d, i) => {
        const [x, y] = pt(i, 100);
        return <line key={d} x1={CX} y1={CY} x2={x} y2={y} className={values[i] === null ? "axis axis-missing" : "axis"} />;
      })}
      {RINGS.map((r) => (
        <text key={`l${r}`} x={CX - 5} y={CY - (R * r) / 100 + 11} textAnchor="end" className="ring-label">
          {r}
        </text>
      ))}
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
      {DIMENSIONS.map((d, i) => {
        const a = angle(i);
        const lx = CX + (R + 16) * Math.cos(a);
        const ly = CY + (R + 16) * Math.sin(a);
        const cos = Math.cos(a);
        const sin = Math.sin(a);
        const anchor = cos > 0.3 ? "start" : cos < -0.3 ? "end" : "middle";
        const words = DIMENSION_LABELS[d].split(" ");
        const lines = [...words, values[i] === null ? "no data" : String(Math.round(values[i]!))];
        const lineH = 14;
        const startY = sin < -0.5 ? ly - (lines.length - 1) * lineH - 2 : sin > 0.5 ? ly + 10 : ly - ((lines.length - 1) * lineH) / 2 + 4;
        return (
          <text key={`t${d}`} x={lx} y={startY} textAnchor={anchor} className="axis-label">
            {lines.map((ln, k) => (
              <tspan
                key={k}
                x={lx}
                dy={k === 0 ? 0 : lineH}
                className={k === lines.length - 1 ? (values[i] === null ? "axis-nodata" : "axis-value") : undefined}
              >
                {ln}
              </tspan>
            ))}
          </text>
        );
      })}
    </svg>
  );
}
