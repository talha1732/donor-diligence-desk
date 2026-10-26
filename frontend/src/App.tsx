import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { ApiError, liveApi, mockApi } from "./api";
import type { DiligenceRequest, Health, OrgSearchResult, RunEvent, Weights } from "./types";
import { initialRunState, runReducer } from "./runState";
import { playEvents, type Player } from "./player";
import { STALL_MS, pollSavedRun, recoveryEvents } from "./recover";
import { MOCK_ORGS, SAMPLE_EVENTS } from "./mock/sampleEvents";
import { cleanName, niceName } from "./format";
import { ChooseScreen, MAX_CHARITIES, type Selected } from "./components/ChooseScreen";
import { MAX_BUDGET, PrioritiesScreen } from "./components/PrioritiesScreen";
import { LiveRun } from "./components/LiveRun";
import { MemoView } from "./components/Memo";
import { EvidenceDrawer, EvidenceLedger } from "./components/Evidence";
import { PastRuns } from "./components/PastRuns";
import { EvidenceContext, Notice, Spinner } from "./components/common";

type View = "choose" | "priorities" | "run" | "memo" | "evidence" | "runs";

interface Params {
  mock: boolean;
  replay: string | null;
  run: string | null;
  speed: number;
  tab: string | null;
  step: string | null;
  q: string | null;
  state: string | null;
}

function readParams(): Params {
  const p = new URLSearchParams(window.location.search);
  const speedRaw = p.get("speed");
  const speed = speedRaw === null || speedRaw === "" || Number.isNaN(Number(speedRaw)) ? 4 : Math.max(0, Number(speedRaw));
  return {
    mock: p.get("mock") === "1" || p.get("mock") === "true",
    replay: p.get("replay"),
    run: p.get("run"),
    speed,
    tab: p.get("tab"),
    step: p.get("step"),
    q: p.get("q"),
    state: p.get("state"),
  };
}

const TAB_TO_VIEW: Record<string, View> = { run: "run", memo: "memo", evidence: "evidence" };
const VIEW_TO_TAB: Partial<Record<View, string>> = { run: "run", memo: "memo", evidence: "evidence" };

function initialView(p: Params): View {
  if (p.step === "1") return "choose";
  if (p.step === "2") return "priorities";
  if (p.step === "runs") return "runs";
  if (p.run) return TAB_TO_VIEW[p.tab ?? ""] ?? "memo";
  if (p.replay || p.mock) return TAB_TO_VIEW[p.tab ?? ""] ?? "run";
  return "choose";
}

const EQUAL_WEIGHTS: Weights = { financial_health: 3, revenue_resilience: 3, cost_discipline: 3, transparency: 3, impact_evidence: 3 };

export default function App() {
  const params = useMemo(readParams, []);
  const api = params.mock ? mockApi : liveApi;
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [view, setView] = useState<View>(() => initialView(params));
  const [selected, setSelected] = useState<Selected[]>([]);
  const [weights, setWeights] = useState<Weights>(EQUAL_WEIGHTS);
  const [note, setNote] = useState("");
  const [budget, setBudget] = useState(0.1);
  const budgetTouched = useRef(false);
  const [defensesOff, setDefensesOff] = useState(false);
  const [run, dispatch] = useReducer(runReducer, initialRunState);
  const [replaying, setReplaying] = useState(false);
  const [replayLabel, setReplayLabel] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<string[]>([]);
  // Saved or replayed runs are stored data; a live run started from this page is live again.
  const [reconnecting, setReconnecting] = useState(false);
  const [viewingSaved, setViewingSaved] = useState(() => !params.mock && !!(params.run || params.replay));
  const playerRef = useRef<Player | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const startReplay = useCallback((events: RunEvent[], speed: number, label: string) => {
    playerRef.current?.cancel();
    abortRef.current?.abort();
    dispatch({ type: "reset" });
    setReplayLabel(label);
    setReplaying(speed > 0);
    playerRef.current = playEvents(
      events,
      speed,
      (batch) => dispatch({ type: "batch", events: batch }),
      () => setReplaying(false),
    );
  }, []);

  // Startup: health, then whichever URL mode was requested.
  useEffect(() => {
    api
      .health()
      .then((h) => {
        setHealth(h);
        if (!budgetTouched.current && h.run_budget_usd > 0) setBudget(Math.min(MAX_BUDGET, h.run_budget_usd));
      })
      .catch((e: Error) => setHealthError(e.message));

    if (params.mock && (params.step === "1" || params.step === "2")) {
      const pick = (ein: string) => MOCK_ORGS.find((o) => o.ein === ein)!;
      setSelected([
        { org: pick("000000001"), website_url: "" },
        { org: pick("061063025"), website_url: "https://www.ctfoodshare.org/" },
      ]);
      if (params.step === "2") {
        setWeights({ financial_health: 3, revenue_resilience: 2, cost_discipline: 2, transparency: 3, impact_evidence: 4 });
        setNote("I care about food insecurity in New Haven, especially families with children.");
      }
      return;
    }
    if (params.step) return;

    const load = async () => {
      try {
        if (params.run) {
          setLoading("Loading the saved run...");
          const result = await api.run(params.run);
          const events = await api.runEvents(params.run).catch(() => null);
          dispatch({ type: "reset" });
          if (events?.length) dispatch({ type: "batch", events });
          dispatch({ type: "loadResult", result });
        } else if (params.replay) {
          setLoading("Loading the run log...");
          const events = await api.runEvents(params.replay);
          if (!events?.length) throw new ApiError(`No event log was found for run ${params.replay}.`, 404);
          startReplay(events, params.speed, `Replay of run ${params.replay}`);
        } else if (params.mock) {
          startReplay(SAMPLE_EVENTS, params.speed, "Sample run");
        }
      } catch (e) {
        setLoadError((e as Error).message);
      } finally {
        setLoading(null);
      }
    };
    void load();
    return () => playerRef.current?.cancel();
  }, [api, params, startReplay]);

  // Keep ?tab= in step with the visible tab for saved, replayed, and mock runs; give finished live runs a link.
  useEffect(() => {
    const tab = VIEW_TO_TAB[view];
    if (!tab) return;
    const p = new URLSearchParams(window.location.search);
    if (p.has("mock") || p.has("replay")) {
      p.set("tab", tab);
    } else if ((run.status === "done" || run.status === "error") && run.runId && run.result) {
      p.set("run", run.runId);
      p.set("tab", tab);
    } else if (p.has("run") && run.runId !== p.get("run")) {
      // A new live run replaced the saved one; drop the stale link until it finishes.
      p.delete("run");
      p.delete("tab");
    } else if (p.has("run")) {
      p.set("tab", tab);
    } else return;
    p.delete("step");
    window.history.replaceState(null, "", `?${p.toString()}`);
  }, [view, run.status, run.runId, run.result]);

  const addOrg = (org: OrgSearchResult) =>
    setSelected((s) => (s.length >= MAX_CHARITIES || s.some((x) => x.org.ein === org.ein) ? s : [...s, { org, website_url: "" }]));
  const removeOrg = (ein: string) => setSelected((s) => s.filter((x) => x.org.ein !== ein));
  const setWebsite = (ein: string, url: string) => setSelected((s) => s.map((x) => (x.org.ein === ein ? { ...x, website_url: url } : x)));

  const startRun = async () => {
    setStartError(null);
    if (api.mock) {
      setView("run");
      startReplay(SAMPLE_EVENTS, params.speed || 4, "Sample run");
      return;
    }
    const req: DiligenceRequest = {
      charities: selected.map((s) => ({ ein: s.org.ein, website_url: s.website_url.trim() || null })),
      weights,
      donor_note: note.trim(),
      budget_usd: budget,
      defenses_off: defensesOff,
    };
    playerRef.current?.cancel();
    abortRef.current?.abort();
    setViewingSaved(false);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setReplaying(false);
    setReplayLabel(null);
    setStarting(true);
    dispatch({ type: "connecting" });
    let sawAny = false;
    let sawEnd = false;
    let recovered = false;
    let runId: string | null = null;
    let lastEventAt = Date.now();
    let streamOpen = true;
    let recovery: Promise<boolean> | null = null;
    const closedMessage = "The connection closed before the run finished. If the server is still running, the run may appear under Past runs.";

    // If the stream goes quiet or closes without `final`, load the run the server saved and rebuild the screen
    // from it, exactly as the final event would have. Only one poll loop runs at a time.
    const recover = (): Promise<boolean> =>
      (recovery ??= (async () => {
        const id = runId!;
        const saved = await pollSavedRun(api, id, ctrl.signal, {
          keepGoing: () => !sawEnd && (!streamOpen || Date.now() - lastEventAt >= STALL_MS),
          direct: () => !streamOpen,
        });
        recovery = null;
        if (saved && !sawEnd && !ctrl.signal.aborted) {
          sawEnd = true;
          recovered = true;
          const { reset, events } = recoveryEvents(saved);
          if (reset) dispatch({ type: "reset" });
          dispatch({ type: "batch", events });
          ctrl.abort(); // nothing more is needed from the quiet stream
          return true;
        }
        if (!saved && streamOpen && !sawEnd && !ctrl.signal.aborted && Date.now() - lastEventAt >= STALL_MS) {
          // Quiet for longer than the server's run timeout and never saved: stop waiting.
          sawEnd = true;
          ctrl.abort();
          dispatch({ type: "fail", message: "The run stopped sending updates and was not saved in time. If the server is still running, the run may appear under Past runs." });
        }
        return false;
      })());

    const watchdog = window.setInterval(() => {
      if (!sawEnd && runId && streamOpen && !recovery && Date.now() - lastEventAt >= STALL_MS) void recover();
    }, 1000);

    try {
      const streamDone = api.stream(
        req,
        (e) => {
          if (recovered) return;
          lastEventAt = Date.now();
          if (!sawAny) {
            sawAny = true;
            setStarting(false);
            setView("run");
          }
          if (e.type === "run_started") runId = e.data.run_id;
          if (e.type === "final" || e.type === "error") sawEnd = true;
          dispatch({ type: "event", event: e });
        },
        ctrl.signal,
      );
      setView("run");
      await streamDone;
      streamOpen = false;
      if (!sawEnd && !ctrl.signal.aborted) {
        setReconnecting(!!runId);
        const ok = runId ? await (recovery ?? recover()) : false;
        if (!ok && !sawEnd && !ctrl.signal.aborted) dispatch({ type: "fail", message: closedMessage });
      }
    } catch (e) {
      streamOpen = false;
      if (ctrl.signal.aborted) return;
      const msg = (e as Error).message;
      if (!sawAny) {
        dispatch({ type: "reset" });
        setView("priorities");
        setStartError(msg);
      } else {
        setReconnecting(!!runId && !sawEnd);
        const ok = runId && !sawEnd ? await (recovery ?? recover()) : false;
        if (!ok && !sawEnd && !ctrl.signal.aborted) dispatch({ type: "fail", message: msg });
      }
    } finally {
      window.clearInterval(watchdog);
      setReconnecting(false);
      setStarting(false);
    }
  };

  const stopWatching = () => {
    abortRef.current?.abort();
    dispatch({ type: "fail", message: "You stopped watching this run. The server may still finish it; check Past runs in a minute." });
  };

  const skip = () => playerRef.current?.skipToEnd();

  const evidence = run.result?.evidence ?? {};
  const openEvidence = useCallback((id: string) => setDrawer((s) => (s[s.length - 1] === id ? s : [...s, id])), []);
  const closeDrawer = useCallback(() => setDrawer([]), []);
  const backDrawer = useCallback(() => setDrawer((s) => s.slice(0, -1)), []);
  const orgName = (ein: string | null | undefined) => {
    const o = run.result?.orgs.find((x) => x.ein === ein) ?? run.charities.find((x) => x.ein === ein);
    return o ? (o.is_demo ? `${cleanName(o.name)} (DEMO)` : niceName(o.name)) : ein ?? "";
  };

  const hasRun = run.status !== "idle";
  const hasResult = !!run.result;
  const steps: { n: number; label: string; view: View; enabled: boolean }[] = [
    { n: 1, label: "Choose charities", view: "choose", enabled: true },
    { n: 2, label: "Set priorities", view: "priorities", enabled: selected.length > 0 },
    { n: 3, label: hasResult ? "Run log" : "Watch the run", view: "run", enabled: hasRun },
    { n: 4, label: "Read the memo", view: "memo", enabled: hasRun },
  ];
  const activeStep = view === "evidence" ? 0 : steps.find((s) => s.view === view)?.n ?? 0;

  const model = run.result?.usage.model ?? run.model ?? health?.model ?? null;
  const dataMode = params.mock
    ? { label: "Sample data", tone: "pill", help: "Mock mode: a bundled sample run replays in your browser. No server or AI calls." }
    : viewingSaved
      ? { label: "Saved run", tone: "pill", help: "You are viewing a stored run. Nothing is sent to the model." }
      : health?.offline_mode
        ? { label: "Offline data", tone: "pill pill-warn", help: "Offline mode: IRS data comes from the bundled cache, not the live ProPublica API." }
        : { label: "Live data", tone: "pill pill-live", help: "Searches and new runs use the live ProPublica Nonprofit Explorer API and the model." };

  const goRun = (runId: string) => {
    const p = new URLSearchParams();
    if (params.mock) p.set("mock", "1");
    p.set("run", runId);
    window.location.search = p.toString();
  };

  return (
    <EvidenceContext.Provider value={{ evidence, open: openEvidence }}>
      <div className="app">
        <header className="topbar no-print">
          <div className="topbar-inner">
            <a className="brand" href={params.mock ? "?mock=1&step=1" : "./"}>
              <span className="brand-mark" aria-hidden>
                D
              </span>
              <span>
                <span className="brand-name">Donor Diligence Desk</span>
                <span className="brand-sub">Investment-committee style giving memos from IRS Form 990 data</span>
              </span>
            </a>
            <nav className="topnav">
              <span className="topmeta">
                <span className={`${dataMode.tone} mode-pill`} title={dataMode.help}>
                  {dataMode.label}
                </span>
                {model && <span className="topmodel">Model: {model}</span>}
              </span>
              <button className={`btn btn-ghost${view === "runs" ? " is-active" : ""}`} type="button" onClick={() => setView("runs")}>
                Past runs
              </button>
              <button className="btn btn-secondary" type="button" onClick={() => setView("choose")}>
                New memo
              </button>
            </nav>
          </div>
          <div className="stepbar">
            <ol className="steps">
              {steps.map((s) => (
                <li key={s.n}>
                  <button
                    type="button"
                    className={`step${activeStep === s.n ? " is-current" : ""}${activeStep > s.n || (s.n >= 3 && hasResult && activeStep !== s.n) ? " is-done" : ""}`}
                    disabled={!s.enabled}
                    onClick={() => setView(s.view)}
                    aria-current={activeStep === s.n ? "step" : undefined}
                  >
                    <span className="step-num">{s.n}</span>
                    <span className="step-label">{s.label}</span>
                  </button>
                </li>
              ))}
              <li className="step-sep" aria-hidden />
              <li>
                <button type="button" className={`step step-tab${view === "evidence" ? " is-current" : ""}`} disabled={!hasResult} onClick={() => setView("evidence")}>
                  <span className="step-label">Evidence ledger</span>
                  {hasResult && <span className="step-count">{Object.keys(evidence).length}</span>}
                </button>
              </li>
            </ol>
          </div>
        </header>

        <div className="banners no-print">
          {params.mock && (
            <div className="modebar">
              <strong>Mock mode:</strong> a bundled sample run replays in your browser, with no server and no API calls. Website
              excerpts, agent text, and scores are sample data. <a href="./">Leave mock mode</a>
            </div>
          )}
          {!params.mock && replayLabel && (
            <div className="modebar">
              <strong>{replayLabel}.</strong> Recorded events are replayed{params.speed > 0 ? ` at ${params.speed}x speed` : ""}; nothing is sent to the model.
            </div>
          )}
          {!params.mock && health && !health.portkey_key_set && (
            <div className="wrap">
              <Notice
                tone="info"
                title="Live runs need an API key"
                action={
                  <button className="btn btn-secondary" type="button" onClick={() => setView("runs")}>
                    Open past runs
                  </button>
                }
              >
                To run new memos, add a line <code>PORTKEY_API_KEY=your-key</code> to a file named <code>.env</code> in the repo folder
                or the folder above it, then restart <code>python backend/run.py</code>. Until then you can browse saved sample runs
                under Past runs, or open <a href="?mock=1">mock mode</a>.
              </Notice>
            </div>
          )}
          {!params.mock && healthError && (
            <div className="wrap">
              <Notice tone="warn" title="The app server is not responding">
                {healthError} Start it with <code>python backend/run.py</code> and reload this page, or try the interface in{" "}
                <a href="?mock=1">mock mode</a>.
              </Notice>
            </div>
          )}
        </div>

        <main className="wrap main">
          {loading && (
            <p className="muted">
              <Spinner /> {loading}
            </p>
          )}
          {loadError && (
            <Notice tone="error" title="Could not open that run" action={<button className="btn btn-secondary" type="button" onClick={() => setView("runs")}>Past runs</button>}>
              {loadError}
            </Notice>
          )}

          {view === "choose" && (
            <ChooseScreen
              api={api}
              selected={selected}
              onAdd={addOrg}
              onRemove={removeOrg}
              onWebsite={setWebsite}
              onNext={() => setView("priorities")}
              initialQuery={params.q}
              initialState={params.state}
            />
          )}
          {view === "priorities" && (
            <PrioritiesScreen
              health={health}
              selected={selected}
              weights={weights}
              setWeights={setWeights}
              note={note}
              setNote={setNote}
              budget={budget}
              setBudget={(b) => {
                budgetTouched.current = true;
                setBudget(b);
              }}
              defensesOff={defensesOff}
              setDefensesOff={setDefensesOff}
              onBack={() => setView("choose")}
              onStart={startRun}
              starting={starting}
              startError={startError}
              canRunLive={!!health?.portkey_key_set}
              mock={api.mock}
            />
          )}
          {view === "run" && hasRun && (
            <LiveRun
              run={run}
              replaying={replaying}
              onSkip={skip}
              onOpenMemo={() => setView("memo")}
              onCancel={api.mock || replaying ? undefined : stopWatching}
              modeNote={
                reconnecting && run.status === "running" ? (
                  <Notice tone="info" title="Reconnecting">
                    <Spinner /> The live connection closed before the last update. Checking every few seconds whether the server
                    saved the finished run (up to 4 minutes).
                  </Notice>
                ) : undefined
              }
            />
          )}
          {view === "run" && !hasRun && !loading && !loadError && <EmptyRun onStart={() => setView("choose")} />}
          {view === "memo" &&
            (run.result ? (
              <MemoView result={run.result} onShowRunLog={() => setView("run")} />
            ) : hasRun ? (
              <div className="card placeholder">
                <h2>The memo appears here when the run finishes</h2>
                <p className="muted">
                  {run.status === "error" ? "This run stopped before a memo was written." : (
                    <>
                      <Spinner /> The agents are still working.
                    </>
                  )}
                </p>
                <button className="btn btn-secondary" type="button" onClick={() => setView("run")}>
                  Watch the run
                </button>
              </div>
            ) : (
              !loading && !loadError && <EmptyRun onStart={() => setView("choose")} />
            ))}
          {view === "evidence" &&
            (run.result ? <EvidenceLedger result={run.result} evidence={evidence} /> : !loading && <EmptyRun onStart={() => setView("choose")} />)}
          {view === "runs" && <PastRuns api={api} onOpen={goRun} />}
        </main>

        <footer className="pagefoot no-print">
          <div className="wrap">
            Decision support, not financial, legal, or tax advice. Data from IRS Form 990 filings via ProPublica Nonprofit Explorer.
            Scores use a documented rubric, which is a hypothesis, not a fact. Yale SOM MGT 409 final project.
          </div>
        </footer>

        <EvidenceDrawer stack={drawer} onClose={closeDrawer} onBack={backDrawer} orgName={orgName} />
      </div>
    </EvidenceContext.Provider>
  );
}

function EmptyRun({ onStart }: { onStart: () => void }) {
  return (
    <div className="card placeholder">
      <h2>No run yet</h2>
      <p className="muted">Pick charities and priorities first, or open a saved run from Past runs.</p>
      <button className="btn btn-primary" type="button" onClick={onStart}>
        Start with step 1
      </button>
    </div>
  );
}
