import { useEffect, useState } from "react";
import type { Health, Weights } from "../types";
import { DIMENSIONS, DIMENSION_LABELS } from "../types";
import { DIMENSION_HELP, IMPORTANCE } from "../labels";
import { fmtCost } from "../format";
import type { Selected } from "./ChooseScreen";
import { Notice, OrgName, Spinner } from "./common";

export const NOTE_MAX = 500;
export const MAX_BUDGET = 0.5;

interface Props {
  health: Health | null;
  selected: Selected[];
  weights: Weights;
  setWeights: (w: Weights) => void;
  note: string;
  setNote: (n: string) => void;
  budget: number;
  setBudget: (b: number) => void;
  defensesOff: boolean;
  setDefensesOff: (v: boolean) => void;
  onBack: () => void;
  onStart: () => void;
  starting: boolean;
  startError: string | null;
  canRunLive: boolean;
  mock: boolean;
}

export function PrioritiesScreen(p: Props) {
  const total = DIMENSIONS.reduce((s, d) => s + p.weights[d], 0);
  const budgetOk = p.budget > 0 && p.budget <= MAX_BUDGET;
  const [budgetText, setBudgetText] = useState(p.budget.toFixed(2));
  useEffect(() => {
    if (Number(budgetText) !== p.budget) setBudgetText(p.budget.toFixed(2));
    // Only react to outside changes (for example the server default arriving).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.budget]);

  return (
    <div className="screen">
      <div className="screen-intro">
        <h1>Set your priorities</h1>
        <p className="lead">
          Tell the agents what matters to you. Weights change how the five scores combine into one overall score. They
          never change the underlying facts.
        </p>
      </div>

      <div className="split">
        <div className="split-main">
          <section className="card">
            <header className="card-head">
              <h3>How much does each factor matter to you?</h3>
              <button className="btn-link" type="button" onClick={() => p.setWeights({ financial_health: 3, revenue_resilience: 3, cost_discipline: 3, transparency: 3, impact_evidence: 3 })}>
                Reset to equal
              </button>
            </header>
            <div className="sliders">
              <div className="slider-row slider-head" aria-hidden>
                <span>Factor</span>
                <span>Importance (0 to 5)</span>
                <span />
                <span>Share of overall score</span>
              </div>
              {DIMENSIONS.map((d) => {
                const v = p.weights[d];
                const share = total > 0 ? v / total : 1 / DIMENSIONS.length;
                return (
                  <div className="slider-row" key={d}>
                    <div className="slider-text">
                      <label htmlFor={`w-${d}`} className="slider-label">
                        {DIMENSION_LABELS[d]}
                      </label>
                      <div className="muted small">{DIMENSION_HELP[d]}</div>
                    </div>
                    <input
                      id={`w-${d}`}
                      type="range"
                      min={0}
                      max={5}
                      step={1}
                      value={v}
                      onChange={(e) => p.setWeights({ ...p.weights, [d]: Number(e.target.value) })}
                      style={{ ["--fill" as string]: `${(v / 5) * 100}%` }}
                    />
                    <div className="slider-value">
                      <strong>{v}</strong>
                      <span className="muted small">{IMPORTANCE[v] ?? ""}</span>
                    </div>
                    <div className="slider-share" title="Share of the overall score">
                      <div className="share-bar">
                        <span style={{ width: `${share * 100}%` }} />
                      </div>
                      <span className="small muted">{Math.round(share * 100)}%</span>
                    </div>
                  </div>
                );
              })}
            </div>
            {total === 0 && <p className="muted small">All weights are zero, so the five factors will count equally.</p>}
          </section>

        </div>

        <aside className="split-side">
          <div className="card sticky">
            <header className="card-head">
              <h3>Ready to run</h3>
            </header>
            <ol className="mini-list">
              {p.selected.map((s) => (
                <li key={s.org.ein}>
                  <OrgName name={s.org.name} isDemo={s.org.is_demo} />
                </li>
              ))}
            </ol>

            <div className="field">
              <div className="field-row">
                <label className="field-label" htmlFor="donor-note">
                  A note to the analysts (optional)
                </label>
                <span className={`small ${p.note.length > NOTE_MAX - 50 ? "warn-text" : "muted"}`}>
                  {p.note.length} / {NOTE_MAX}
                </span>
              </div>
              <textarea
                id="donor-note"
                rows={3}
                maxLength={NOTE_MAX}
                value={p.note}
                onChange={(e) => p.setNote(e.target.value.slice(0, NOTE_MAX))}
                placeholder="I care about food insecurity in New Haven"
              />
              <span className="muted small">Used to judge mission fit. Instructions aimed at the AI are screened out.</span>
            </div>

            <label className="field">
              <span className="field-label">Spending cap for this run (USD)</span>
              <div className="money-input">
                <span>$</span>
                <input
                  type="number"
                  min={0.01}
                  max={MAX_BUDGET}
                  step={0.01}
                  value={budgetText}
                  onChange={(e) => {
                    setBudgetText(e.target.value);
                    p.setBudget(Number(e.target.value));
                  }}
                  onBlur={() => budgetOk && setBudgetText(p.budget.toFixed(2))}
                  className={budgetOk ? "" : "invalid"}
                />
              </div>
              {!budgetOk && <span className="field-error">Enter an amount above $0 and at most ${MAX_BUDGET.toFixed(2)}.</span>}
              <span className="muted small">
                The run stops safely at this cap and keeps what it has. Maximum ${MAX_BUDGET.toFixed(2)}.
                {p.health && !p.mock && (
                  <>
                    {" "}
                    Spent today on this server: {fmtCost(p.health.daily_spent_usd)} of the ${p.health.daily_budget_usd.toFixed(2)} daily cap.
                  </>
                )}
              </span>
            </label>

            {p.health?.allow_defense_toggle && (
              <label className="check">
                <input type="checkbox" checked={p.defensesOff} onChange={(e) => p.setDefensesOff(e.target.checked)} />
                <span>
                  Turn safety defenses off <span className="muted small">(safety demo only: shows what the attack does)</span>
                </span>
              </label>
            )}

            {p.startError && <Notice tone="error" title="The run did not start">{p.startError}</Notice>}
            {!p.canRunLive && !p.mock && (
              <Notice tone="warn">Live runs need an API key on the server. See the note at the top of the page.</Notice>
            )}

            <button className="btn btn-primary btn-block btn-lg" type="button" onClick={p.onStart} disabled={p.starting || !budgetOk || p.selected.length === 0 || (!p.canRunLive && !p.mock)}>
              {p.starting ? <Spinner /> : null}
              Start the diligence run
            </button>
            <p className="muted small center">
              {p.mock ? "Mock mode: replays a saved sample run, no API calls." : "Takes about two minutes. You can watch every step."}
            </p>
            <button className="btn btn-ghost btn-block" type="button" onClick={p.onBack}>
              Back to charities
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}
