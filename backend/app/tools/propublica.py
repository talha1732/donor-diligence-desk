"""ProPublica Nonprofit Explorer API client (owner: data and scoring builder).

API docs: https://projects.propublica.org/nonprofits/api
- Search:  GET https://projects.propublica.org/nonprofits/api/v2/search.json?q=<name>&state%5Bid%5D=<ST>
           Search matches organization names; use the state filter rather than putting the state in q.
- Org:     GET https://projects.propublica.org/nonprofits/api/v2/organizations/<ein>.json
           Returns organization{...}, filings_with_data[...], filings_without_data[...].

Requirements:
- Disk cache in backend/data/cache/propublica/ (org_<ein>.json, search_<hash>.json). Cache hits skip
  the network. OFFLINE_MODE=1 means cache only.
- Demo fixtures: fictional charities with EINs starting "00000000" live in
  backend/data/cache/propublica/demo_<ein>.json and are always served from disk with is_demo=True.
- Map raw ProPublica filing fields to FilingYear (see docs/contract.md section 3 for the mapping).

Cache files hold the raw API response unchanged, plus one extra top-level key "_cache" with
{fetched_at, source_url}. Demo fixtures use the same raw shape plus a "_demo" key.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.schemas import FilingYear, OrgProfile, OrgSearchResult

API_BASE = "https://projects.propublica.org/nonprofits/api/v2"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "propublica"
USER_AGENT = (
    "DonorDiligenceDesk/1.0 (Yale SOM MGT 409 course project; giving-memo research tool; "
    "contact via course staff)"
)
TIMEOUT = httpx.Timeout(20.0, connect=10.0)
RETRY_DELAY_S = 1.0
DEMO_PREFIX = "00000000"

# Real charities committed to the cache for one-click demos, in display order.
FEATURED_EINS: tuple[str, ...] = (
    "061063025",  # Connecticut Foodshare, Wallingford CT
    "222511873",  # Columbus House, New Haven CT
    "060653044",  # Integrated Refugee & Immigrant Services (IRIS), New Haven CT
    "061178712",  # Habitat for Humanity of Greater New Haven (IRS name: Habitat For Humanity International Inc)
    "363673599",  # Feeding America, Chicago IL
    "271661997",  # GiveDirectly, New York NY
    "133433452",  # Doctors Without Borders USA (Medecins Sans Frontieres Usa Inc), New York NY
)

# Official websites for the featured charities, checked by hand on 2026-10-25.
FEATURED_WEBSITES: dict[str, str] = {
    "061063025": "https://www.ctfoodshare.org/",
    "222511873": "https://www.columbushouse.org/",
    "060653044": "https://irisct.org/",
    "061178712": "https://www.habitatnh.org/",
    "363673599": "https://www.feedingamerica.org/",
    "271661997": "https://www.givedirectly.org/",
    "133433452": "https://www.doctorswithoutborders.org/",
}

FORM_TYPES: dict[int, str] = {0: "990", 1: "990EZ", 2: "990PF"}

# FilingYear attribute -> raw ProPublica keys. Several keys are summed; a missing key makes the value None.
_COMMON: dict[str, tuple[str, ...]] = {
    "total_revenue": ("totrevenue",),
    "total_expenses": ("totfuncexpns",),
    "total_assets": ("totassetsend",),
    "total_liabilities": ("totliabend",),
}
FIELD_SOURCES: dict[str, dict[str, tuple[str, ...]]] = {
    "990": {
        **_COMMON,
        "net_assets": ("totnetassetend",),
        "contributions": ("totcntrbgfts",),
        "program_service_revenue": ("totprgmrevnue",),
        "investment_income": ("invstmntinc",),
        "officer_compensation": ("compnsatncurrofcr",),
        "other_salaries": ("othrsalwages",),
        "payroll_tax": ("payrolltx",),
        "professional_fundraising_fees": ("profndraising",),
        "fundraising_event_gross": ("grsincfndrsng",),
        "fundraising_event_direct_expenses": ("lessdirfndrsng",),
    },
    # 990EZ Part I has no officer, salary, payroll-tax or professional-fundraising lines.
    "990EZ": {
        **_COMMON,
        "net_assets": ("totnetassetsend",),
        "contributions": ("totcntrbs",),
        "program_service_revenue": ("prgmservrev",),
        "investment_income": ("othrinvstinc",),
        "fundraising_event_gross": ("grsrevnuefndrsng",),
        "fundraising_event_direct_expenses": ("direxpns",),
    },
    # 990PF Part I: lines 3 + 4 (interest, dividends) correspond to Form 990 investment income.
    "990PF": {
        **_COMMON,
        "net_assets": ("tfundnworth",),
        "contributions": ("grscontrgifts",),
        "investment_income": ("intrstrvnue", "dividndsamt"),
        "officer_compensation": ("compofficers",),
    },
}
MONEY_FIELDS: tuple[str, ...] = (
    "total_revenue",
    "total_expenses",
    "total_assets",
    "total_liabilities",
    "net_assets",
    "contributions",
    "program_service_revenue",
    "investment_income",
    "officer_compensation",
    "other_salaries",
    "payroll_tax",
    "professional_fundraising_fees",
    "fundraising_event_gross",
    "fundraising_event_direct_expenses",
)


class OrgNotFound(Exception):
    pass


class ProPublicaUnavailable(OrgNotFound):
    """The API could not be reached and no cached copy exists. Subclasses OrgNotFound so callers that
    only catch OrgNotFound still handle it."""


# --------------------------------------------------------------------------- helpers


def offline_mode() -> bool:
    return os.environ.get("OFFLINE_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}


def normalize_ein(ein: str | int | None) -> str | None:
    """'06-1063025', 61063025 and '061063025' all become '061063025'. None if not a valid EIN."""
    if ein is None or isinstance(ein, bool):
        return None
    digits = re.sub(r"[\s-]", "", str(ein))
    if not digits.isdigit() or not 1 <= len(digits) <= 9:
        return None
    return digits.zfill(9)


def is_demo_ein(ein: str) -> bool:
    return ein.startswith(DEMO_PREFIX)


def org_api_url(ein: str) -> str:
    return f"{API_BASE}/organizations/{ein}.json"


def org_page_url(ein: str) -> str:
    """Human-readable ProPublica page. ProPublica's canonical URL drops leading zeros (it 301s otherwise)."""
    return f"https://projects.propublica.org/nonprofits/organizations/{int(ein)}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _org_cache_path(ein: str) -> Path:
    return CACHE_DIR / f"org_{ein}.json"


def _demo_path(ein: str) -> Path:
    return CACHE_DIR / f"demo_{ein}.json"


def _search_key(query: str, state: str | None) -> str:
    payload = json.dumps({"q": query.strip().lower(), "state": state or ""}, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _search_cache_path(query: str, state: str | None) -> Path:
    return CACHE_DIR / f"search_{_search_key(query, state)}.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=TIMEOUT,
        follow_redirects=True,
    )


async def _get_json(url: str, params: dict[str, str] | None = None) -> dict[str, Any] | None:
    """GET JSON with one retry. Returns None on 404; raises ProPublicaUnavailable on other failures."""
    last_error = "unknown error"
    async with _make_client() as client:
        for attempt in range(2):
            if attempt:
                await asyncio.sleep(RETRY_DELAY_S)
            try:
                resp = await client.get(url, params=params)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                continue
            if resp.status_code != 200:
                raise ProPublicaUnavailable(f"ProPublica returned HTTP {resp.status_code} for {url}")
            try:
                data = resp.json()
            except ValueError:
                last_error = "response was not JSON"
                continue
            if not isinstance(data, dict):
                last_error = "unexpected JSON shape"
                continue
            return data
    raise ProPublicaUnavailable(f"ProPublica API unavailable for {url}: {last_error}")


# --------------------------------------------------------------------------- mapping


def _num(raw: dict[str, Any], key: str) -> float | None:
    value = raw.get(key)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _sum_fields(raw: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    values = [_num(raw, k) for k in keys]
    if any(v is None for v in values):
        return None
    return float(sum(values))  # type: ignore[arg-type]


def raw_source_for(form_type: str | None, field: str) -> tuple[str, ...]:
    """Raw ProPublica keys that feed a FilingYear field for this form type (empty if unmapped)."""
    return FIELD_SOURCES.get(form_type or "", _COMMON).get(field, ())


def map_filing(raw: dict[str, Any]) -> FilingYear | None:
    """Map one raw filings_with_data entry to FilingYear. Returns None if it has no tax year."""
    tax_period = raw.get("tax_prd")
    tax_period = int(tax_period) if isinstance(tax_period, (int, float)) and not isinstance(tax_period, bool) else None
    tax_year = raw.get("tax_prd_yr")
    if not isinstance(tax_year, int) or isinstance(tax_year, bool):
        tax_year = tax_period // 100 if tax_period else None
    if not tax_year:
        return None
    formtype = raw.get("formtype")
    form_type = FORM_TYPES.get(formtype) if isinstance(formtype, int) else None
    sources = FIELD_SOURCES.get(form_type or "", _COMMON)
    values: dict[str, float | None] = {field: _sum_fields(raw, keys) for field, keys in sources.items()}
    if form_type == "990EZ" and (_num(raw, "grsincgaming") or 0) != 0:
        # Line 6c combines gaming and fundraising-event direct expenses; it is only clean without gaming.
        values["fundraising_event_direct_expenses"] = None
    pdf_url = raw.get("pdf_url") or None
    return FilingYear(
        tax_year=tax_year,
        tax_period=tax_period,
        form_type=form_type,
        pdf_url=pdf_url if isinstance(pdf_url, str) else None,
        **values,
    )


def _filings_from_raw(raw_filings: list[Any]) -> list[FilingYear]:
    """Newest first, one filing per tax year (the later tax period wins after a fiscal-year change)."""
    mapped = [f for f in (map_filing(r) for r in raw_filings if isinstance(r, dict)) if f is not None]
    mapped.sort(key=lambda f: (f.tax_year, f.tax_period or 0), reverse=True)
    seen: set[int] = set()
    out: list[FilingYear] = []
    for filing in mapped:
        if filing.tax_year in seen:
            continue
        seen.add(filing.tax_year)
        out.append(filing)
    return out


def profile_from_raw(
    raw: dict[str, Any],
    *,
    source_url: str,
    fetched_at: str,
    from_cache: bool,
    is_demo: bool = False,
    website_url: str | None = None,
) -> OrgProfile:
    org = raw.get("organization") or {}
    ein = normalize_ein(org.get("ein"))
    if not ein or not org.get("name"):
        raise OrgNotFound("ProPublica response has no organization record")
    filings = _filings_from_raw(raw.get("filings_with_data") or [])
    with_data = {f.tax_year for f in filings}
    without: set[int] = set()
    for item in raw.get("filings_without_data") or []:
        year = item.get("tax_prd_yr") if isinstance(item, dict) else None
        if isinstance(year, int) and not isinstance(year, bool) and year not in with_data:
            without.add(year)
    subsection = org.get("subsection_code")
    ruling = org.get("ruling_date")
    return OrgProfile(
        ein=ein,
        name=str(org["name"]).strip(),
        city=org.get("city") or None,
        state=org.get("state") or None,
        ntee_code=org.get("ntee_code") or None,
        subsection_code=subsection if isinstance(subsection, int) and not isinstance(subsection, bool) else None,
        ruling_date=str(ruling) if ruling else None,
        is_demo=is_demo,
        website_url=website_url,
        source_url=source_url,
        filings=filings,
        filings_without_data_years=sorted(without, reverse=True),
        fetched_at=fetched_at,
        from_cache=from_cache,
    )


def _profile_from_cache_file(raw: dict[str, Any], ein: str) -> OrgProfile:
    meta = raw.get("_cache") or {}
    return profile_from_raw(
        raw,
        source_url=meta.get("source_url") or org_api_url(ein),
        fetched_at=meta.get("fetched_at") or _now_iso(),
        from_cache=True,
        website_url=FEATURED_WEBSITES.get(ein) or meta.get("website_url"),
    )


def _profile_from_demo_file(raw: dict[str, Any], ein: str) -> OrgProfile:
    meta = raw.get("_demo") or {}
    return profile_from_raw(
        raw,
        source_url=f"fixture:demo_{ein}.json",
        fetched_at=meta.get("created_at") or _now_iso(),
        from_cache=True,
        is_demo=True,
        website_url=meta.get("website_url"),
    )


def load_cached_profile(ein: str) -> OrgProfile | None:
    """Profile from the demo fixture or org cache on disk, without any network access."""
    norm = normalize_ein(ein)
    if not norm:
        return None
    if is_demo_ein(norm):
        raw = _read_json(_demo_path(norm))
        return _profile_from_demo_file(raw, norm) if raw else None
    raw = _read_json(_org_cache_path(norm))
    if not raw:
        return None
    try:
        return _profile_from_cache_file(raw, norm)
    except OrgNotFound:
        return None


def _search_result_from_profile(profile: OrgProfile) -> OrgSearchResult:
    return OrgSearchResult(
        ein=profile.ein,
        name=profile.name,
        city=profile.city,
        state=profile.state,
        ntee_code=profile.ntee_code,
        subsection_code=profile.subsection_code,
        latest_revenue=profile.filings[0].total_revenue if profile.filings else None,
        is_demo=profile.is_demo,
    )


def _search_result_from_raw(item: dict[str, Any]) -> OrgSearchResult | None:
    ein = normalize_ein(item.get("ein")) or normalize_ein(item.get("strein"))
    name = item.get("name")
    if not ein or not name:
        return None
    subsection = item.get("subseccd")
    cached = load_cached_profile(ein)
    latest_revenue = cached.filings[0].total_revenue if cached and cached.filings else None
    return OrgSearchResult(
        ein=ein,
        name=str(name).strip(),
        city=item.get("city") or None,
        state=item.get("state") or None,
        ntee_code=item.get("ntee_code") or None,
        subsection_code=subsection if isinstance(subsection, int) and not isinstance(subsection, bool) else None,
        latest_revenue=latest_revenue,
        is_demo=is_demo_ein(ein),
    )


def _demo_eins() -> list[str]:
    eins = []
    for path in sorted(CACHE_DIR.glob("demo_*.json")):
        ein = normalize_ein(path.stem.removeprefix("demo_"))
        if ein and is_demo_ein(ein):
            eins.append(ein)
    return eins


def _cached_org_eins() -> list[str]:
    eins = []
    for path in sorted(CACHE_DIR.glob("org_*.json")):
        ein = normalize_ein(path.stem.removeprefix("org_"))
        if ein:
            eins.append(ein)
    return eins


def _name_matches(name: str, query: str) -> bool:
    tokens = [t for t in re.split(r"\W+", query.lower()) if t]
    hay = name.lower()
    return bool(tokens) and all(t in hay for t in tokens)


def _local_search(query: str, state: str | None, *, include_real: bool) -> list[OrgSearchResult]:
    eins = _demo_eins() + (_cached_org_eins() if include_real else [])
    out = []
    for ein in eins:
        profile = load_cached_profile(ein)
        if profile is None or not _name_matches(profile.name, query):
            continue
        if state and (profile.state or "").upper() != state:
            continue
        out.append(_search_result_from_profile(profile))
    return out


# --------------------------------------------------------------------------- public API


async def search_orgs(query: str, state: str | None = None, limit: int = 10) -> list[OrgSearchResult]:
    """Name search. DEMO fixtures that match come first. A 9-digit EIN query looks the EIN up directly.
    When offline or when the API is unreachable, falls back to cached organizations whose names match."""
    query = (query or "").strip()
    limit = max(1, min(int(limit), 25))
    if not query:
        return []
    state = state.strip().upper() if state and state.strip() else None
    if state and not re.fullmatch(r"[A-Z]{2}", state):
        state = None

    digits = re.sub(r"[\s-]", "", query)
    if digits.isdigit() and len(digits) == 9:
        try:
            profile = await get_org_profile(digits, require_filings=False)
        except OrgNotFound:
            return []
        return [_search_result_from_profile(profile)]

    results = _local_search(query, state, include_real=False)
    path = _search_cache_path(query, state)
    raw = _read_json(path)
    if raw is None and not offline_mode():
        params = {"q": query}
        if state:
            params["state[id]"] = state
        try:
            raw = await _get_json(f"{API_BASE}/search.json", params=params)
        except ProPublicaUnavailable:
            raw = None
        if raw is not None:
            raw["_cache"] = {"fetched_at": _now_iso(), "query": query, "state": state}
            _write_json(path, raw)
    if raw is None:
        results += _local_search(query, state, include_real=True)
    else:
        for item in raw.get("organizations") or []:
            if isinstance(item, dict):
                mapped = _search_result_from_raw(item)
                if mapped is not None:
                    results.append(mapped)

    seen: set[str] = set()
    unique = []
    for r in results:
        if r.ein not in seen:
            seen.add(r.ein)
            unique.append(r)
    return unique[:limit]


async def get_org_profile(ein: str, *, require_filings: bool = True, refresh: bool = False) -> OrgProfile:
    """Raise OrgNotFound when the EIN does not exist or has no data.

    require_filings=False returns organizations that exist but have no filings with data.
    refresh=True skips the cache read and re-fetches (still writes the cache)."""
    norm = normalize_ein(ein)
    if not norm:
        raise OrgNotFound(f"{ein!r} is not a valid 9-digit EIN")

    if is_demo_ein(norm):
        raw = _read_json(_demo_path(norm))
        if raw is None:
            raise OrgNotFound(f"No DEMO fixture for EIN {norm}")
        return _check_filings(_profile_from_demo_file(raw, norm), require_filings)

    path = _org_cache_path(norm)
    raw = None if refresh else _read_json(path)
    if raw is not None:
        return _check_filings(_profile_from_cache_file(raw, norm), require_filings)
    if offline_mode():
        raise OrgNotFound(f"EIN {norm} is not in the local cache and OFFLINE_MODE=1")

    url = org_api_url(norm)
    raw = await _get_json(url)
    if raw is None or not raw.get("organization"):
        raise OrgNotFound(f"ProPublica has no organization with EIN {norm}")
    fetched_at = _now_iso()
    raw["_cache"] = {"fetched_at": fetched_at, "source_url": url}
    _write_json(path, raw)
    profile = profile_from_raw(
        raw,
        source_url=url,
        fetched_at=fetched_at,
        from_cache=False,
        website_url=FEATURED_WEBSITES.get(norm),
    )
    return _check_filings(profile, require_filings)


def _check_filings(profile: OrgProfile, require_filings: bool) -> OrgProfile:
    if require_filings and not profile.filings:
        raise OrgNotFound(
            f"{profile.name} (EIN {profile.ein}) has no Form 990 financial data in ProPublica's extract"
        )
    return profile


def list_featured_orgs() -> list[OrgSearchResult]:
    """Charities with cached data for one-click demos (DEMO fixtures first, then real cached orgs)."""
    out = []
    for ein in [*_demo_eins(), *FEATURED_EINS]:
        profile = load_cached_profile(ein)
        if profile is not None and profile.filings:
            out.append(_search_result_from_profile(profile))
    return out
