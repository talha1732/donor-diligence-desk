import type { ReactNode } from "react";
import type { RunState, AgentView } from "../runState";
import { elapsedSeconds } from "../runState";
import { STAGES } from "../types";
import { ROLE_DUTY, ROLE_TITLES, SECURITY_TITLES, SEVERITY_LABELS, STAGE_HELP, STAGE_LABELS, TOOL_LABELS } from "../labels";
import { cleanName, fmtCost, fmtInt, fmtSeconds, niceName, truncate } from "../format";
import { DemoBadge, Notice, Spinner } from "./common";
import { describeTool, plainSecurityDetail } from "../toolText";

interface Props {
  run: RunState;
  replaying: boolean;
  onSkip: () => void;
  onOpenMemo: () => void;
  onCancel?: () => void;
  modeNote?: ReactNode;
}

export function charityName(run: RunState, ein: string | null | undefined): string {
  if (!ein) return "All charities";
  const c = run.charities.find((x) => x.ein === ein);
  if (!c) return `EIN ${ein}`;
  return c.is_demo ? cleanName(c.name) : niceName(c.name);
}

export function agentTitle(run: RunState, key: string): string {
  const a = run.agents[key];
  const role = ROLE_TITLES[a?.role ?? "other"];
  return a?.ein ? `${role}, ${charityName(run, a.ein)}` : role;
}

export function LiveRun({ run, replaying, onSkip, onOpenMemo, onCancel, modeNote }: Props) {
  const running = run.status === "running" || run.status === "connecting";
  const resultStatus = run.result?.status;
  const charityEins = run.charities.map((c) => c.ein);
  const teamKeys = run.agentOrder.filter((k) => !run.agents[k].ein);
  const otherKeys = run.agentOrder.filter((k) => run.agents[k].ein && !charityEins.includes(run.agents[k].ein!));

  return (
    <div className="screen">
      <div className="run-head">
        <div>
          <div className="eyebrow">Step 3 · Watch the agents work</div>
          <h1>
            {running ? "Diligence run in progress" : run.status === "error" ? "The run stopped early" : "Diligence run complete"}
          </h1>
          <div className="run-meta">
            <StatusPill run={run} />
            {run.runId && <span>Run {run.runId}</span>}
            {run.model && <span>Model {run.model}</span>}
            <span>{fmtSeconds(elapsedSeconds(run))} elapsed</span>
            <span className={run.defensesOn ? "pill pill-ok" : "pill pill-bad"}>{run.defensesOn ? "Safety defenses on" : "Safety defenses off"}</span>
          </div>
        </div>
        <div className="run-actions">
          {replaying && running && (
            <button className="btn btn-secondary" type="button" onClick={onSkip}>
              Skip to the end
            </button>
          )}
          {onCancel && running && !replaying && (
            <button className="btn btn-ghost" type="button" onClick={onCancel}>
              Stop watching
            </button>
          )}
          {run.result?.memo && !(run.status === "done" && resultStatus === "complete") && (
            <button className="btn btn-primary" type="button" onClick={onOpenMemo}>
              Read the memo
            </button>
          )}
        </div>
      </div>

      {modeNote}

      {run.status === "connecting" && (
        <Notice tone="info" title="Connecting">
          <Spinner /> Starting the run on the server...
        </Notice>
      )}
      {run.error && (
        <Notice tone="error" title="The run reported an error" action={run.result?.memo ? <button className="btn btn-secondary" type="button" onClick={onOpenMemo}>See the partial memo</button> : undefined}>
          {run.error}
          {run.result ? " The parts that finished are kept below and in the memo tab." : ""}
        </Notice>
      )}
      {resultStatus === "stopped_budget" && (
        <Notice tone="warn" title="Stopped at the spending cap">
          The run reached its budget, so the remaining agents were cancelled. The memo uses the work that finished.
        </Notice>
      )}
      {run.status === "done" && resultStatus === "complete" && run.result?.memo && (
        <Notice tone="success" title="The memo is ready." action={<button className="btn btn-primary" type="button" onClick={onOpenMemo}>Read the memo</button>}>
          {run.result.memo.headline}
        </Notice>
      )}

      <StageStepper run={run} />

      <div className="run-grid">
        <div className="run-main">
          {run.charities.map((c) => (
            <section className="agent-group" key={c.ein}>
              <h2 className="group-title">
                {c.is_demo ? cleanName(c.name) : niceName(c.name)} {c.is_demo && <DemoBadge />}
              </h2>
              <div className="agent-cards">
                {[`financial:${c.ein}`, `impact:${c.ein}`].filter((k) => run.agents[k]).map((k) => (
                  <AgentCard key={k} agent={run.agents[k]} />
                ))}
              </div>
            </section>
          ))}
          {otherKeys.length > 0 && (
            <section className="agent-group">
              <h2 className="group-title">Other agents</h2>
              <div className="agent-cards">
                {otherKeys.map((k) => (
                  <AgentCard key={k} agent={run.agents[k]} />
                ))}
              </div>
            </section>
          )}
          <section className="agent-group">
            <h2 className="group-title">Review and writing</h2>
            <div className="agent-cards">
              {teamKeys.map((k) => (
                <AgentCard key={k} agent={run.agents[k]} />
              ))}
            </div>
          </section>
        </div>

        <aside className="run-side">
          <SpendMeter run={run} />
          <SecurityPanel run={run} />
          <div className="card evidence-count">
            <div className="stat-label">Evidence ledger</div>
            <div className="stat-big">{fmtInt(run.result ? Object.keys(run.result.evidence).length : run.evidenceIds.length)}</div>
            <div className="muted small">entries: IRS fields, calculations, website excerpts, and your note. Every number in the memo must match one.</div>
          </div>
        </aside>
      </div>

      <ToolLog run={run} />
    </div>
  );
}

function StatusPill({ run }: { run: RunState }) {
  if (run.status === "running" || run.status === "connecting")
    return (
      <span className="pill pill-live">
        <span className="live-dot" /> Running
      </span>
    );
  if (run.status === "error") return <span className="pill pill-bad">Error</span>;
  if (run.result?.status === "stopped_budget") return <span className="pill pill-warn">Stopped at budget</span>;
  return <span className="pill pill-ok">Complete</span>;
}

function StageStepper({ run }: { run: RunState }) {
  return (
    <ol className="stages" aria-label="Run stages">
      {STAGES.map((s, i) => {
        const st = run.stages[s];
        return (
          <li key={s} className={`stage stage-${st}`}>
            <span className="stage-num">{st === "done" ? "✓" : st === "stopped" ? "!" : i + 1}</span>
            <span className="stage-text">
              <strong>{STAGE_LABELS[s]}</strong>
              <span className="small">{STAGE_HELP[s]}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

const STATUS_TEXT: Record<AgentView["status"], string> = {
  waiting: "Waiting",
  running: "Working",
  done: "Done",
  error: "Stopped",
  stopped: "Stopped",
};

function AgentCard({ agent }: { agent: AgentView }) {
  const recent = agent.toolCalls.slice(-3);
  const u = agent.usage;
  return (
    <article className={`agent-card agent-${agent.status}`}>
      <header>
        <div>
          <h3>{ROLE_TITLES[agent.role]}</h3>
          <div className="muted small">{ROLE_DUTY[agent.role]}</div>
        </div>
        <span className={`agent-status status-${agent.status}`}>
          {agent.status === "running" && <span className="live-dot" />}
          {STATUS_TEXT[agent.status]}
        </span>
      </header>
      <div className="agent-activity">
        <span className="activity-label">{agent.status === "done" ? "Result" : "Now"}</span>
        <span>{agent.status === "done" || agent.status === "error" ? agent.summary || agent.activity : agent.activity}</span>
      </div>
      {recent.length > 0 && (
        <ul className="agent-tools">
          {recent.map((t, i) => {
            const d = describeTool(t);
            return (
              <li key={i} title={`Technical detail: ${d.raw}`}>
                <span className="tool-text">{truncate(d.text, 90)}</span>
                {d.result && <span className="muted">{truncate(d.result, 90)}</span>}
              </li>
            );
          })}
          {agent.toolCalls.length > 3 && <li className="muted small">and {agent.toolCalls.length - 3} earlier</li>}
        </ul>
      )}
      <footer className="agent-foot">
        <span>{agent.toolCalls.length || u?.tool_calls || 0} tool uses</span>
        {u && (
          <>
            <span>{fmtInt(u.input_tokens + u.output_tokens)} tokens</span>
            <span>{fmtCost(u.cost_usd)}</span>
            <span>{fmtSeconds(u.seconds)}</span>
          </>
        )}
      </footer>
    </article>
  );
}

function ToolLog({ run }: { run: RunState }) {
  const start = run.firstTs ? Date.parse(run.firstTs) : 0;
  const rows = [...run.toolLog].reverse();
  return (
    <section className="card tool-log">
      <header className="card-head">
        <h3>What the agents did</h3>
        <span className="muted small">{run.toolLog.length} tool uses, newest first. The tools return the numbers; the AI only reads them.</span>
      </header>
      {rows.length === 0 ? (
        <p className="muted empty">Each tool the agents use appears here as they work.</p>
      ) : (
        <div className="table-wrap">
          <table className="table toollog-table">
            <colgroup>
              <col style={{ width: 72 }} />
              <col style={{ width: 250 }} />
              <col style={{ width: 330 }} />
              <col />
              <col style={{ width: 230 }} />
            </colgroup>
            <thead>
              <tr>
                <th>Time</th>
                <th>Agent</th>
                <th>What it did</th>
                <th>Result</th>
                <th>Technical detail</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t, i) => {
                const d = describeTool(t);
                return (
                  <tr key={i}>
                    <td className="mono nowrap">+{((Date.parse(t.ts) - start) / 1000).toFixed(1)}s</td>
                    <td>{agentTitle(run, t.agent)}</td>
                    <td title={TOOL_LABELS[t.tool] ?? t.tool}>{d.text}</td>
                    <td>{d.result}</td>
                    <td className="mono args muted" title={`${d.raw}${t.result_summary ? ` -> ${t.result_summary}` : ""}${t.ms != null ? ` (${fmtInt(t.ms)} ms)` : ""}`}>
                      {truncate(d.raw, 60)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function SpendMeter({ run }: { run: RunState }) {
  const u = run.usage;
  const budget = u?.budget_usd ?? run.budgetUsd ?? 0;
  const cost = u?.total.cost_usd ?? 0;
  const pct = budget > 0 ? Math.min(1, cost / budget) : 0;
  const t = u?.total;
  const cachedPct = t && t.input_tokens > 0 ? t.cached_tokens / t.input_tokens : 0;
  return (
    <section className="card spend">
      <header className="card-head">
        <h3>Spend</h3>
        <span className="muted small">{u?.model ?? run.model ?? ""}</span>
      </header>
      <div className="spend-figure">
        <span className="stat-big">{fmtCost(cost)}</span>
        <span className="muted">of ${budget.toFixed(2)} cap</span>
      </div>
      <div className={`meter${pct > 0.8 ? " meter-hot" : ""}`} role="meter" aria-valuemin={0} aria-valuemax={budget} aria-valuenow={cost} aria-label="Spend against budget">
        <span style={{ width: `${Math.max(pct * 100, cost > 0 ? 1.5 : 0)}%` }} />
      </div>
      <div className="muted small">{(pct * 100).toFixed(1)}% of the run budget used</div>
      <dl className="token-grid">
        <div>
          <dt>Input tokens</dt>
          <dd>{fmtInt(t?.input_tokens)}</dd>
        </div>
        <div>
          <dt>Cached</dt>
          <dd>
            {fmtInt(t?.cached_tokens)} <span className="muted small">({Math.round(cachedPct * 100)}%)</span>
          </dd>
        </div>
        <div>
          <dt>Output tokens</dt>
          <dd>{fmtInt(t?.output_tokens)}</dd>
        </div>
        <div>
          <dt>Model requests</dt>
          <dd>{fmtInt(t?.requests)}</dd>
        </div>
      </dl>
      <p className="muted small">Cached input is billed at a tenth of the normal input price.</p>
    </section>
  );
}

const SNIPPET_LABELS: Record<string, string> = {
  hidden_text_removed: "Example of the hidden text",
  injection_detected: "Instruction that was blocked",
  unverified_claim: "Removed claim",
  url_blocked: "Blocked address",
  input_blocked: "Note that was dropped",
};

export function SecurityPanel({ run, compact }: { run: RunState; compact?: boolean }) {
  return (
    <section className="card security">
      <header className="card-head">
        <h3>Safety defenses</h3>
        <span className={`count-pill${run.security.length ? " count-alert" : ""}`}>{run.security.length} fired</span>
      </header>
      {run.security.length === 0 ? (
        <p className="muted empty">
          Nothing has fired yet. Hidden web text, instructions aimed at the AI, unsafe links, unverified numbers, and budget
          limits are reported here.
        </p>
      ) : (
        <ul className="sec-list">
          {run.security.map((e, i) => (
            <li key={i} className={`sec sec-${e.severity}`}>
              <div className="sec-head">
                <span className={`sev sev-${e.severity}`}>{SEVERITY_LABELS[e.severity]}</span>
                <strong>{SECURITY_TITLES[e.kind] ?? e.kind}</strong>
              </div>
              <div className="muted small">
                {e.agent ? agentTitle(run, e.agent) : e.ein ? charityName(run, e.ein) : "Run"}
              </div>
              <p className="sec-detail">{compact ? truncate(plainSecurityDetail(e.detail), 160) : plainSecurityDetail(e.detail)}</p>
              {e.snippet && (
                <blockquote className="snippet">
                  <span className="snippet-label">{SNIPPET_LABELS[e.kind] ?? "Text that was blocked"}</span>
                  {truncate(e.snippet, 240)}
                </blockquote>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
