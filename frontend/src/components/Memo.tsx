import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { AgentUsage, CharityScorecard, CharitySection, DiligenceResult, Finding, Weights } from "../types";
import { DIMENSIONS, DIMENSION_LABELS, IMPACT_EVIDENCE_LEVELS } from "../types";
import { BAND_LABELS, DIMENSION_HELP, IMPORTANCE, ROLE_TITLES, agentRole } from "../labels";
import { cleanName, fmtCost, fmtDateTime, fmtEin, fmtInt, fmtSeconds, niceName } from "../format";
import { inferHasFilings, rescore, sameWeights, type Rescored } from "../reweight";
import { BandBadge, DemoBadge, Notice, OrgName, SourceChips } from "./common";
import { SpiderChart } from "./SpiderChart";
import { TrendChart } from "./TrendChart";
import { EmailDraft } from "./EmailDraft";

interface Props {
  result: DiligenceResult;
  onShowRunLog: () => void;
}

function displayName(name: string, isDemo: boolean) {
  return isDemo ? cleanName(name) : niceName(name);
}

export function MemoView({ result, onShowRunLog }: Props) {
  const memo = result.memo;
  const sections: CharitySection[] =
    memo?.charities ??
    result.scorecards.map((s) => ({
      ein: s.ein,
      name: s.name,
      is_demo: s.is_demo,
      band: s.band,
      overall: s.overall,
      one_line: "",
      strengths: [],
      concerns: [],
      questions_for_charity: [],
      could_not_verify: [],
    }));
  const cards = new Map(result.scorecards.map((s) => [s.ein, s]));
  const original = result.request.weights;
  const [weights, setWeights] = useState<Weights>(original);
  useEffect(() => setWeights(result.request.weights), [result.run_id]); // eslint-disable-line react-hooks/exhaustive-deps
  const changed = !sameWeights(weights, original);
  const scores = useMemo(() => {
    const out = new Map<string, { now: Rescored; orig: Rescored }>();
    for (const s of sections) {
      const card = cards.get(s.ein);
      const orig: Rescored = { overall: card?.overall ?? s.overall ?? null, band: card?.band ?? s.band };
      let now = orig;
      if (changed && card) {
        const years = result.metrics.find((m) => m.ein === s.ein)?.years_of_data;
        now = rescore(card, weights, inferHasFilings(card, years));
      }
      out.set(s.ein, { now, orig });
    }
    return out;
    // sections and cards derive from result.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, weights, changed]);
  const nameFor = (agent: string) => {
    const ein = agent.split(":")[1];
    const org = result.orgs.find((o) => o.ein === ein);
    return org ? displayName(org.name, org.is_demo) : "";
  };

  return (
    <div className="screen memo-screen">
      <div className="memo-toolbar no-print">
        <div className="muted small">
          Run {result.run_id} · {fmtDateTime(result.created_at)} · {result.usage.model}
        </div>
        <div className="toolbar-actions">
          <button className="btn btn-ghost" type="button" onClick={onShowRunLog}>
            See how it was made
          </button>
          <button className="btn btn-secondary" type="button" onClick={() => window.print()}>
            Print or save as PDF
          </button>
        </div>
      </div>

      {result.status === "stopped_budget" && (
        <Notice tone="warn" title="Partial memo">The run stopped at its spending cap. Sections below use only the work that finished.</Notice>
      )}
      {result.status === "error" && (
        <Notice tone="error" title="Partial result">{result.error ?? "The run stopped with an error."} The sections below use only the work that finished.</Notice>
      )}
      {!result.defenses_on && (
        <Notice tone="error" title="Safety defenses were off for this run">
          This run was made for the safety demonstration. Unverified claims and web text were not filtered, so do not rely on it.
        </Notice>
      )}

      <article className="memo">
        <header className="memo-head">
          <div className="eyebrow">
            Giving memo · {fmtDateTime(result.created_at)} · {sections.length} {sections.length === 1 ? "charity" : "charities"}
          </div>
          <h1 className="memo-headline">{memo?.headline ?? "No memo was written for this run"}</h1>
          {memo?.summary && <p className="memo-summary">{memo.summary}</p>}
          {memo?.recommendation && (
            <div className="recommendation">
              <div className="rec-label">Recommendation</div>
              <p>{memo.recommendation}</p>
            </div>
          )}
          {result.request.donor_note && (
            <p className="muted small donor-note">
              Your note: "{result.request.donor_note}"
            </p>
          )}
        </header>

        <section className="memo-block">
          <h2>At a glance</h2>
          {changed ? (
            <>
              <div className="no-print">
                <GlanceTable sections={sections} cards={cards} scores={scores} weights={weights} original={original} useNow />
              </div>
              <div className="print-only">
                <GlanceTable sections={sections} cards={cards} scores={scores} weights={original} original={original} />
              </div>
            </>
          ) : (
            <GlanceTable sections={sections} cards={cards} scores={scores} weights={original} original={original} />
          )}
          <PrioritiesPanel weights={weights} original={original} onChange={setWeights} />
          <p className="method-note">
            <strong>How scores work.</strong> Each dimension is scored 0 to 100 with a documented rubric applied to IRS Form
            990 data and the charity's own website. The thresholds are a hypothesis, not facts. The overall score is the
            weighted mean of the dimensions that could be scored, using your weights; a dimension with no data is left out, not
            counted as zero. {memo?.method_note}
          </p>
        </section>

        {sections.map((s) => (
          <CharityBlock key={s.ein} section={s} card={cards.get(s.ein)} result={result} score={scores.get(s.ein)!} weights={weights} changed={changed} />
        ))}

        {result.audit && result.audit.auditor_notes.length > 0 && (
          <section className="memo-block">
            <h2>Red-team auditor notes</h2>
            <ul className="plain-list">
              {result.audit.auditor_notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
            <p className="muted small">
              Number check: {result.audit.verification.verified_count} findings verified against the evidence ledger,{" "}
              {result.audit.verification.flagged_count} flagged and kept out of the memo.
            </p>
          </section>
        )}

        <section className="memo-block">
          <h2>What this memo cost</h2>
          <UsageTable agents={result.usage.agents} total={result.usage.total} nameFor={nameFor} budget={result.usage.budget_usd} />
        </section>

        <footer className="memo-foot">
          <p className="disclaimer">{memo?.disclaimer ?? "This memo is decision support, not financial, legal, or tax advice."}</p>
          <p className="muted small">
            Data: IRS Form 990 extracts via the ProPublica Nonprofit Explorer API, and each charity's own website. Charities
            marked DEMO are fictional.
          </p>
        </footer>
      </article>
    </div>
  );
}

type ScoreMap = Map<string, { now: Rescored; orig: Rescored }>;

/** Highest overall first; charities without an overall go last; ties keep memo order. */
function rankOrder(sections: CharitySection[], pick: (ein: string) => number | null): string[] {
  return sections
    .map((s, i) => ({ ein: s.ein, i, v: pick(s.ein) }))
    .sort((a, b) => (a.v === null ? (b.v === null ? a.i - b.i : 1) : b.v === null ? -1 : b.v - a.v || a.i - b.i))
    .map((x) => x.ein);
}

function GlanceTable({
  sections,
  cards,
  scores,
  weights,
  original,
  useNow,
}: {
  sections: CharitySection[];
  cards: Map<string, CharityScorecard>;
  scores: ScoreMap;
  weights: Weights;
  original: Weights;
  useNow?: boolean;
}) {
  const pick = (ein: string) => (useNow ? scores.get(ein)!.now : scores.get(ein)!.orig);
  const order = rankOrder(sections, (ein) => pick(ein).overall);
  const origOrder = rankOrder(sections, (ein) => scores.get(ein)!.orig.overall);
  const byEin = new Map(sections.map((s) => [s.ein, s]));
  const ranked = sections.length > 1;
  return (
    <div className="table-wrap">
      <table className="table glance">
        <thead>
          <tr>
            {ranked && <th className="rank-col">Rank</th>}
            <th>Charity</th>
            <th>Fit</th>
            <th className="num">Overall</th>
            {DIMENSIONS.map((d) => {
              const moved = useNow && weights[d] !== original[d];
              return (
                <th key={d} className="num">
                  {DIMENSION_LABELS[d]}
                  <span className={`th-sub${moved ? " th-changed" : ""}`} title={moved ? `Originally ${original[d]}` : undefined}>
                    weight {weights[d]}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {order.map((ein, idx) => {
            const s = byEin.get(ein)!;
            const card = cards.get(ein);
            const sc = pick(ein);
            const orig = scores.get(ein)!.orig;
            const was = origOrder.indexOf(ein);
            const rankMove = useNow ? was - idx : 0;
            const delta = useNow && sc.overall !== null && orig.overall !== null ? Math.round(sc.overall) - Math.round(orig.overall) : 0;
            return (
              <tr key={ein} className={useNow && (rankMove || delta) ? "row-moved" : undefined}>
                {ranked && (
                  <td className="rank-col">
                    <span className="rank-num">{idx + 1}</span>
                    {rankMove !== 0 && (
                      <span className={`move ${rankMove > 0 ? "move-up" : "move-down"}`} title={`Ranked ${ordinal(was + 1)} with your original priorities`}>
                        {rankMove > 0 ? "▲" : "▼"} {Math.abs(rankMove)}
                      </span>
                    )}
                  </td>
                )}
                <td>
                  <a href={`#charity-${ein}`} className="glance-name">
                    <OrgName name={s.name} isDemo={s.is_demo} />
                  </a>
                </td>
                <td>
                  <BandBadge band={sc.band} />
                </td>
                <td className="num strong overall-cell" title={sc.overall === null ? undefined : `${sc.overall.toFixed(1)} of 100`}>
                  {fmtScore(sc.overall)}
                  {useNow && (
                    <span
                      className={`delta ${delta > 0 ? "delta-up" : delta < 0 ? "delta-down" : "delta-same"}`}
                      title={`${orig.overall === null ? "n/a" : orig.overall.toFixed(1)} with your original priorities`}
                    >
                      {delta > 0 ? `▲ ${delta}` : delta < 0 ? `▼ ${-delta}` : "no change"}
                    </span>
                  )}
                </td>
                {DIMENSIONS.map((d) => {
                  const ds = card?.dimensions.find((x) => x.dimension === d);
                  return (
                    <td key={d} className={`num${ds?.score == null ? " nodata" : ""}`}>
                      {ds?.score == null ? "no data" : Math.round(ds.score)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ordinal(n: number) {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

function PrioritiesPanel({ weights, original, onChange }: { weights: Weights; original: Weights; onChange: (w: Weights) => void }) {
  const changed = !sameWeights(weights, original);
  const total = DIMENSIONS.reduce((sum, d) => sum + weights[d], 0);
  return (
    <section className="reweight no-print" aria-labelledby="reweight-title">
      <header className="reweight-head">
        <div>
          <h3 id="reweight-title">Try different priorities</h3>
          <p className="muted small reweight-note">
            Scores update instantly in your browser. No AI calls: the five dimension scores are fixed calculations, only
            the weights change. The written memo reflects your original priorities.
          </p>
        </div>
        {changed ? (
          <button className="btn-link reweight-reset" type="button" onClick={() => onChange(original)}>
            Reset to your original priorities
          </button>
        ) : (
          <span className="reweight-status small">Showing your original priorities</span>
        )}
      </header>
      <div className="reweight-grid">
        {DIMENSIONS.map((d) => {
          const v = weights[d];
          const share = total > 0 ? v / total : 1 / DIMENSIONS.length;
          const moved = v !== original[d];
          return (
            <div className={`rw-cell${moved ? " is-moved" : ""}`} key={d}>
              <div className="rw-top">
                <label htmlFor={`rw-${d}`} className="rw-label" title={DIMENSION_HELP[d]}>
                  {DIMENSION_LABELS[d]}
                </label>
                <span className="rw-value">{v}</span>
              </div>
              <input
                id={`rw-${d}`}
                type="range"
                min={0}
                max={5}
                step={1}
                value={v}
                onChange={(e) => onChange({ ...weights, [d]: Number(e.target.value) })}
                style={{ ["--fill" as string]: `${(v / 5) * 100}%` }}
                aria-valuetext={`${v}, ${IMPORTANCE[Math.round(v)] ?? ""}`}
              />
              <div className="rw-foot small">
                <span>{IMPORTANCE[Math.round(v)] ?? ""}</span>
                <span className="muted">{moved ? `was ${original[d]}` : `${Math.round(share * 100)}% of overall`}</span>
              </div>
            </div>
          );
        })}
      </div>
      {total === 0 && <p className="muted small reweight-zero">All weights are zero, so the five dimensions count equally, as in the scoring rules.</p>}
    </section>
  );
}

/** Shows the re-weighted value on screen and the original value in print. */
function ScreenPrint({ changed, screen, print }: { changed: boolean; screen: ReactNode; print: ReactNode }) {
  if (!changed) return <>{print}</>;
  return (
    <>
      <span className="no-print">{screen}</span>
      <span className="print-only">{print}</span>
    </>
  );
}

function fmtScore(v: number | null | undefined) {
  return v == null ? "n/a" : String(Math.round(v));
}

function CharityBlock({
  section,
  card,
  result,
  score,
  weights,
  changed,
}: {
  section: CharitySection;
  card?: CharityScorecard;
  result: DiligenceResult;
  score: { now: Rescored; orig: Rescored };
  weights: Weights;
  changed: boolean;
}) {
  const org = result.orgs.find((o) => o.ein === section.ein);
  const impact = result.reports.find((r) => r.ein === section.ein && r.role === "impact")?.impact;
  const name = displayName(section.name, section.is_demo);
  const { now, orig } = score;
  const scoreHead = (sc: Rescored, note?: ReactNode) => (
    <div className="charity-score">
      <BandBadge band={sc.band} large />
      <div className="overall">
        <span className="overall-num">{fmtScore(sc.overall)}</span>
        <span className="overall-of">/ 100 overall</span>
        {note}
      </div>
    </div>
  );
  return (
    <section className="memo-block charity-block" id={`charity-${section.ein}`}>
      <header className="charity-head">
        <div>
          <h2>
            {name} {section.is_demo && <DemoBadge />}
          </h2>
          <div className="muted small">
            {[org?.city, org?.state].filter(Boolean).join(", ")}
            {org?.city || org?.state ? " · " : ""}EIN {fmtEin(section.ein)}
          </div>
        </div>
        {changed ? (
          <>
            <div className="no-print">
              {scoreHead(
                now,
                <span className="overall-was" title="The memo text below uses your original priorities">
                  was {fmtScore(orig.overall)}
                  {now.band !== orig.band ? `, ${BAND_LABELS[orig.band]}` : ""}
                </span>,
              )}
            </div>
            <div className="print-only">{scoreHead(orig)}</div>
          </>
        ) : (
          scoreHead(orig)
        )}
      </header>
      {section.one_line && <p className="one-line">{section.one_line}</p>}

      {card && (
        <div className="score-grid">
          <div className="score-side">
            <figure className="spider-wrap">
              <SpiderChart dimensions={card.dimensions} title={`Scores for ${name}`} />
              <figcaption className="muted small">Shared 0 to 100 scale for every charity. Gaps mean no data, not zero.</figcaption>
            </figure>
            <TrendChart ein={section.ein} name={name} />
          </div>
          <div className="dims">
            {DIMENSIONS.map((d) => {
              const ds = card.dimensions.find((x) => x.dimension === d);
              const score = ds?.score;
              return (
                <div className="dim" key={d}>
                  <div className="dim-top">
                    <span className="dim-label">{DIMENSION_LABELS[d]}</span>
                    <span className="dim-weight muted small">
                      <ScreenPrint
                        changed={changed && weights[d] !== result.request.weights[d]}
                        screen={<span className="weight-changed">weight {weights[d]}</span>}
                        print={<>weight {ds?.weight ?? result.request.weights[d]}</>}
                      />
                    </span>
                    <span className={`dim-score${score == null ? " nodata" : ""}`}>{score == null ? "no data" : Math.round(score)}</span>
                  </div>
                  <div className="dim-bar">
                    <span style={{ width: `${score == null ? 0 : score}%` }} />
                  </div>
                  {ds?.explanation && <p className="dim-expl">{ds.explanation}</p>}
                  {d === "impact_evidence" && impact && (
                    <p className="muted small">
                      Evidence level {impact.evidence_level} of 4: {impact.evidence_level_label || IMPACT_EVIDENCE_LEVELS[impact.evidence_level]}
                    </p>
                  )}
                  {ds && ds.drivers.length > 0 && <SourceChips ids={ds.drivers} limit={5} />}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="two-col">
        <FindingList title="Strengths" tone="strength" findings={section.strengths} empty="No verified strengths." />
        <FindingList title="Concerns" tone="concern" findings={section.concerns} empty="No verified concerns." />
      </div>

      <div className="two-col">
        <div>
          <h3 className="list-title">Questions to ask the charity</h3>
          {section.questions_for_charity.length ? (
            <ol className="questions">
              {section.questions_for_charity.map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ol>
          ) : null}
          {section.questions_for_charity.length > 0 && <EmailDraft name={name} questions={section.questions_for_charity} />}
          {section.questions_for_charity.length === 0 && (
            <p className="muted">None.</p>
          )}
        </div>
        <div>
          <h3 className="list-title">Could not verify</h3>
          {section.could_not_verify.length ? (
            <ul className="cnv">
              {section.could_not_verify.map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">Nothing outstanding.</p>
          )}
          <p className="muted small">Missing values are left blank and turned into questions. The app never guesses a number.</p>
        </div>
      </div>
    </section>
  );
}

const DIM_SHORT: Record<string, string> = { ...DIMENSION_LABELS, mission_fit: "Mission fit", other: "Other" };

function FindingList({ title, tone, findings, empty }: { title: string; tone: "strength" | "concern"; findings: Finding[]; empty: string }) {
  return (
    <div>
      <h3 className={`list-title list-${tone}`}>{title}</h3>
      {findings.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <ul className={`findings findings-${tone}`}>
          {findings.map((f) => (
            <li key={f.id}>
              <span className="finding-dim">{DIM_SHORT[f.dimension] ?? f.dimension}</span>
              <p>{f.text}</p>
              <SourceChips ids={f.evidence_ids} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function UsageTable({ agents, total, nameFor, budget }: { agents: AgentUsage[]; total: AgentUsage; nameFor: (agent: string) => string; budget?: number }) {
  return (
    <div className="table-wrap">
      <table className="table usage">
        <thead>
          <tr>
            <th>Agent</th>
            <th className="num">Requests</th>
            <th className="num">Input tokens</th>
            <th className="num">Cached</th>
            <th className="num">Output tokens</th>
            <th className="num">Tool calls</th>
            <th className="num">Cost</th>
            <th className="num">Seconds</th>
          </tr>
        </thead>
        <tbody>
          {agents.map((a) => {
            const role = ROLE_TITLES[agentRole(a.agent)];
            const who = nameFor(a.agent);
            return (
              <tr key={a.agent}>
                <td>
                  {role}
                  {who && <span className="muted">, {who}</span>}
                </td>
                <td className="num">{fmtInt(a.requests)}</td>
                <td className="num">{fmtInt(a.input_tokens)}</td>
                <td className="num">{fmtInt(a.cached_tokens)}</td>
                <td className="num">{fmtInt(a.output_tokens)}</td>
                <td className="num">{fmtInt(a.tool_calls)}</td>
                <td className="num">{fmtCost(a.cost_usd)}</td>
                <td className="num">{fmtSeconds(a.seconds)}</td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <td>Total{budget ? <span className="muted"> (cap ${budget.toFixed(2)})</span> : null}</td>
            <td className="num">{fmtInt(total.requests)}</td>
            <td className="num">{fmtInt(total.input_tokens)}</td>
            <td className="num">{fmtInt(total.cached_tokens)}</td>
            <td className="num">{fmtInt(total.output_tokens)}</td>
            <td className="num">{fmtInt(total.tool_calls)}</td>
            <td className="num">{fmtCost(total.cost_usd)}</td>
            <td className="num">{fmtSeconds(total.seconds)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
