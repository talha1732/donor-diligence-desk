import { useEffect, useState, type FormEvent } from "react";
import type { Api } from "../api";
import type { OrgSearchResult } from "../types";
import { fmtEin, fmtUsd } from "../format";
import { Notice, OrgName, Spinner } from "./common";

export interface Selected {
  org: OrgSearchResult;
  website_url: string;
}

export const MAX_CHARITIES = 3;

interface Props {
  api: Api;
  selected: Selected[];
  onAdd: (org: OrgSearchResult) => void;
  onRemove: (ein: string) => void;
  onWebsite: (ein: string, url: string) => void;
  onNext: () => void;
  initialQuery?: string | null;
  initialState?: string | null;
}

export function websiteError(url: string): string | null {
  const v = url.trim();
  if (!v) return null;
  if (!/^https?:\/\//i.test(v)) return "Start with http:// or https://";
  if (v.length > 500) return "Keep it under 500 characters";
  return null;
}

export function ChooseScreen({ api, selected, onAdd, onRemove, onWebsite, onNext, initialQuery, initialState }: Props) {
  const [featured, setFeatured] = useState<OrgSearchResult[] | null>(null);
  const [featuredError, setFeaturedError] = useState<string | null>(null);
  const [q, setQ] = useState(initialQuery ?? "");
  const [state, setState] = useState((initialState ?? "").slice(0, 2).toUpperCase());
  const [results, setResults] = useState<OrgSearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [lastQuery, setLastQuery] = useState({ q: "", state: "" });

  useEffect(() => {
    api
      .featured()
      .then((r) => setFeatured([...r].sort((a, b) => Number(b.is_demo) - Number(a.is_demo))))
      .catch((e: Error) => setFeaturedError(e.message));
  }, [api]);

  const runSearch = async (query: string, st: string) => {
    setSearching(true);
    setSearchError(null);
    setLastQuery({ q: query, state: st });
    try {
      setResults(await api.search(query, st));
    } catch (e) {
      setSearchError((e as Error).message);
      setResults(null);
    } finally {
      setSearching(false);
    }
  };

  const search = (ev: FormEvent) => {
    ev.preventDefault();
    if (q.trim()) void runSearch(q.trim(), state.trim().toUpperCase());
  };

  useEffect(() => {
    if (initialQuery?.trim()) void runSearch(initialQuery.trim(), (initialState ?? "").slice(0, 2).toUpperCase());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isSelected = (ein: string) => selected.some((s) => s.org.ein === ein);
  const full = selected.length >= MAX_CHARITIES;
  const hasErrors = selected.some((s) => websiteError(s.website_url));

  return (
    <div className="screen">
      <div className="screen-intro">
        <h1>Choose up to three charities</h1>
        <p className="lead">Search any US charity by name or EIN, or add a featured one below.</p>
      </div>

      <ol className="howto" aria-label="How it works">
        <li>
          <span className="howto-num">1</span>
          <span>
            <strong>Pick charities.</strong> Up to three to compare.
          </span>
        </li>
        <li>
          <span className="howto-num">2</span>
          <span>
            <strong>Set priorities.</strong> Say what matters most to you.
          </span>
        </li>
        <li>
          <span className="howto-num">3</span>
          <span>
            <strong>Watch the agents.</strong> They read IRS filings and websites, about two minutes.
          </span>
        </li>
        <li>
          <span className="howto-num">4</span>
          <span>
            <strong>Read the memo.</strong> Every number links to its source.
          </span>
        </li>
      </ol>

      <div className="split">
        <div className="split-main">
          <form className="search" onSubmit={search} role="search">
            <label className="field grow">
              <span className="field-label">Charity name or EIN</span>
              <input
                type="search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="For example: food bank, Columbus House, or 06-1063025"
                autoFocus
              />
            </label>
            <label className="field state-field">
              <span className="field-label">State</span>
              <input
                value={state}
                onChange={(e) => setState(e.target.value.replace(/[^a-z]/gi, "").slice(0, 2).toUpperCase())}
                placeholder="CT"
                maxLength={2}
                aria-label="Two-letter state code (optional)"
              />
            </label>
            <button className="btn btn-primary" type="submit" disabled={searching || !q.trim()}>
              {searching ? <Spinner /> : null}
              Search
            </button>
          </form>

          {searchError && <Notice tone="error" title="Search did not work">{searchError}</Notice>}

          {results && (
            <section className="results">
              <div className="section-head">
                <h2>
                  {results.length} result{results.length === 1 ? "" : "s"} for "{lastQuery.q}"
                  {lastQuery.state ? ` in ${lastQuery.state}` : ""}
                </h2>
                <button className="btn-link" type="button" onClick={() => setResults(null)}>
                  Clear
                </button>
              </div>
              {results.length === 0 ? (
                <p className="muted">No matches. Try a shorter name, drop the state filter, or paste the EIN.</p>
              ) : (
                <ul className="org-list">
                  {results.map((o) => (
                    <OrgRow key={o.ein} org={o} selected={isSelected(o.ein)} disabled={full} onAdd={() => onAdd(o)} onRemove={() => onRemove(o.ein)} />
                  ))}
                </ul>
              )}
            </section>
          )}

          <section className="featured">
            <div className="section-head">
              <h2>Featured charities</h2>
              <span className="muted small">One click to add. DEMO charities are fictional and work without internet.</span>
            </div>
            {featuredError && <Notice tone="warn" title="Could not load featured charities">{featuredError}</Notice>}
            {!featured && !featuredError && (
              <p className="muted">
                <Spinner /> Loading...
              </p>
            )}
            {featured && (
              <div className="org-grid">
                {featured.map((o) => (
                  <OrgCard key={o.ein} org={o} selected={isSelected(o.ein)} disabled={full} onAdd={() => onAdd(o)} onRemove={() => onRemove(o.ein)} />
                ))}
              </div>
            )}
          </section>
        </div>

        <aside className="split-side">
          <div className="card shortlist sticky">
            <header className="card-head">
              <h3>Your shortlist</h3>
              <span className="count-pill">
                {selected.length} of {MAX_CHARITIES}
              </span>
            </header>
            {selected.length === 0 ? (
              <p className="muted empty">Add one to three charities from the left. Comparing two or three gives the most useful memo.</p>
            ) : (
              <ol className="shortlist-items">
                {selected.map((s) => {
                  const err = websiteError(s.website_url);
                  return (
                    <li key={s.org.ein}>
                      <div className="shortlist-top">
                        <div>
                          <div className="org-name">
                            <OrgName name={s.org.name} isDemo={s.org.is_demo} />
                          </div>
                          <div className="muted small">
                            {[s.org.city, s.org.state].filter(Boolean).join(", ")} · EIN {fmtEin(s.org.ein)}
                          </div>
                        </div>
                        <button className="btn-icon" type="button" onClick={() => onRemove(s.org.ein)} aria-label={`Remove ${s.org.name}`} title="Remove">
                          ×
                        </button>
                      </div>
                      <label className="field">
                        <span className="field-label">Website (optional)</span>
                        <input
                          value={s.website_url}
                          onChange={(e) => onWebsite(s.org.ein, e.target.value)}
                          placeholder={s.org.is_demo ? "Built-in demo page is used" : "https://"}
                          className={err ? "invalid" : ""}
                        />
                        {err ? <span className="field-error">{err}</span> : null}
                      </label>
                    </li>
                  );
                })}
              </ol>
            )}
            <button className="btn btn-primary btn-block" type="button" disabled={selected.length === 0 || hasErrors} onClick={onNext}>
              Next: set your priorities
            </button>
            {full && <p className="muted small center">The shortlist is full. Remove one to add another.</p>}
          </div>
        </aside>
      </div>
    </div>
  );
}

interface OrgProps {
  org: OrgSearchResult;
  selected: boolean;
  disabled: boolean;
  onAdd: () => void;
  onRemove: () => void;
}

function AddButton({ selected, disabled, onAdd, onRemove }: Omit<OrgProps, "org">) {
  if (selected)
    return (
      <button className="btn btn-small btn-selected" type="button" onClick={onRemove} title="Click to remove">
        Added
      </button>
    );
  return (
    <button className="btn btn-small btn-secondary" type="button" onClick={onAdd} disabled={disabled}>
      Add
    </button>
  );
}

function OrgRow({ org, ...rest }: OrgProps) {
  return (
    <li className={`org-row${rest.selected ? " is-selected" : ""}`}>
      <div className="org-row-main">
        <div className="org-name">
          <OrgName name={org.name} isDemo={org.is_demo} />
        </div>
        <div className="org-meta">
          <span>{[org.city, org.state].filter(Boolean).join(", ") || "Location not listed"}</span>
          <span>EIN {fmtEin(org.ein)}</span>
          <span>Latest revenue {org.latest_revenue != null ? fmtUsd(org.latest_revenue) : "not reported"}</span>
        </div>
      </div>
      <AddButton {...rest} />
    </li>
  );
}

function OrgCard({ org, ...rest }: OrgProps) {
  return (
    <div className={`org-card${rest.selected ? " is-selected" : ""}${org.is_demo ? " is-demo" : ""}`}>
      <div className="org-card-body">
        <div className="org-name">
          <OrgName name={org.name} isDemo={org.is_demo} />
        </div>
        <div className="org-meta-stack">
          <span>{[org.city, org.state].filter(Boolean).join(", ") || "Location not listed"}</span>
          <span>EIN {fmtEin(org.ein)}</span>
        </div>
      </div>
      <div className="org-card-foot">
        <div>
          <div className="stat-label">Latest revenue</div>
          <div className="stat-value">{org.latest_revenue != null ? fmtUsd(org.latest_revenue) : "n/a"}</div>
        </div>
        <AddButton {...rest} />
      </div>
    </div>
  );
}
