import type { AgentUsage, CharityScorecard, CharitySection, DiligenceResult, Finding } from "../types";
import { DIMENSIONS, DIMENSION_LABELS, IMPACT_EVIDENCE_LEVELS } from "../types";
import { ROLE_TITLES, agentRole } from "../labels";
import { cleanName, fmtCost, fmtDateTime, fmtEin, fmtInt, fmtSeconds, niceName } from "../format";
import { BandBadge, DemoBadge, Notice, OrgName, SourceChips } from "./common";
import { SpiderChart } from "./SpiderChart";

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
          <GlanceTable sections={sections} cards={cards} result={result} />
          <p className="method-note">
            <strong>How scores work.</strong> Each dimension is scored 0 to 100 with a documented rubric applied to IRS Form
            990 data and the charity's own website. The thresholds are a hypothesis, not facts. The overall score is the
            weighted mean of the dimensions that could be scored, using your weights; a dimension with no data is left out, not
            counted as zero. {memo?.method_note}
          </p>
        </section>

        {sections.map((s) => (
          <CharityBlock key={s.ein} section={s} card={cards.get(s.ein)} result={result} />
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

function GlanceTable({ sections, cards, result }: { sections: CharitySection[]; cards: Map<string, CharityScorecard>; result: DiligenceResult }) {
  const w = result.request.weights;
  return (
    <div className="table-wrap">
      <table className="table glance">
        <thead>
          <tr>
            <th>Charity</th>
            <th>Fit</th>
            <th className="num">Overall</th>
            {DIMENSIONS.map((d) => (
              <th key={d} className="num">
                {DIMENSION_LABELS[d]}
                <span className="th-sub">weight {w[d]}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sections.map((s) => {
            const card = cards.get(s.ein);
            return (
              <tr key={s.ein}>
                <td>
                  <a href={`#charity-${s.ein}`} className="glance-name">
                    <OrgName name={s.name} isDemo={s.is_demo} />
                  </a>
                </td>
                <td>
                  <BandBadge band={card?.band ?? s.band} />
                </td>
                <td className="num strong">{fmtScore(card?.overall ?? s.overall)}</td>
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

function fmtScore(v: number | null | undefined) {
  return v == null ? "n/a" : String(Math.round(v));
}

function CharityBlock({ section, card, result }: { section: CharitySection; card?: CharityScorecard; result: DiligenceResult }) {
  const org = result.orgs.find((o) => o.ein === section.ein);
  const impact = result.reports.find((r) => r.ein === section.ein && r.role === "impact")?.impact;
  const name = displayName(section.name, section.is_demo);
  const band = card?.band ?? section.band;
  const overall = card?.overall ?? section.overall;
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
        <div className="charity-score">
          <BandBadge band={band} large />
          <div className="overall">
            <span className="overall-num">{fmtScore(overall)}</span>
            <span className="overall-of">/ 100 overall</span>
          </div>
        </div>
      </header>
      {section.one_line && <p className="one-line">{section.one_line}</p>}

      {card && (
        <div className="score-grid">
          <figure className="spider-wrap">
            <SpiderChart dimensions={card.dimensions} title={`Scores for ${name}`} />
            <figcaption className="muted small">Shared 0 to 100 scale for every charity. Gaps mean no data, not zero.</figcaption>
          </figure>
          <div className="dims">
            {DIMENSIONS.map((d) => {
              const ds = card.dimensions.find((x) => x.dimension === d);
              const score = ds?.score;
              return (
                <div className="dim" key={d}>
                  <div className="dim-top">
                    <span className="dim-label">{DIMENSION_LABELS[d]}</span>
                    <span className="dim-weight muted small">weight {ds?.weight ?? result.request.weights[d]}</span>
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
          ) : (
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
