"""Raw web access (owner: data and scoring builder).

These functions return RAW content. They do not sanitize. The caller must run
app.safety.guards.check_url() before fetch_url() and app.safety.sanitize.sanitize_html() after it.

Local demo pages: any URL whose host is 127.0.0.1 or localhost and whose path starts with /demo/
is read directly from backend/data/demo_pages/<file> (no network, no self-request).
With OFFLINE_MODE=1, web_search returns [] and fetch_url serves only those local demo pages.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.safety.guards import check_url
from app.schemas import FetchedPage, WebSearchResult
from app.tools.propublica import offline_mode

DEMO_PAGES_DIR = Path(__file__).resolve().parents[2] / "data" / "demo_pages"
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})
# The safety eval serves its attack corpus from one fixed subfolder.
DEMO_SUBFOLDERS = ("", "attacks")
DEMO_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*\.html$")
ALLOWED_CONTENT_TYPES = ("text/html", "text/plain")
MAX_REDIRECTS = 5
SEARCH_TIMEOUT_S = 20.0
SNIPPET_MAX_CHARS = 400
TITLE_MAX_CHARS = 200
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0 Safari/537.36"
)


class _BlockedHost(Exception):
    pass


# --------------------------------------------------------------------------- search


def _ddgs_text(query: str, max_results: int) -> list[dict[str, Any]]:
    from ddgs import DDGS

    with DDGS(timeout=10) as client:
        return list(client.text(query, region="us-en", safesearch="moderate", max_results=max_results) or [])


def _clip(text: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


async def web_search(query: str, max_results: int = 5) -> list[WebSearchResult]:
    """DuckDuckGo via the `ddgs` package (no API key). Return [] on any failure; never raise."""
    try:
        query = (query or "").strip()[:300]
        if not query or offline_mode():
            return []
        max_results = max(1, min(int(max_results), 10))
        raw = await asyncio.wait_for(asyncio.to_thread(_ddgs_text, query, max_results), timeout=SEARCH_TIMEOUT_S)
        out: list[WebSearchResult] = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("href") or item.get("url") or "").strip()
            if not url.lower().startswith(("http://", "https://")):
                continue
            out.append(
                WebSearchResult(
                    title=_clip(item.get("title"), TITLE_MAX_CHARS) or url,
                    url=url,
                    snippet=_clip(item.get("body") or item.get("snippet"), SNIPPET_MAX_CHARS),
                )
            )
        return out[:max_results]
    except Exception:  # noqa: BLE001 - search is best effort by contract
        return []


# --------------------------------------------------------------------------- fetch


def _is_local_host(host: str) -> bool:
    return host.lower() in LOCAL_HOSTS


def _is_private_host(host: str) -> bool:
    """True for localhost and literal private, loopback, link-local or reserved IPs."""
    host = host.strip("[]").lower()
    if host in LOCAL_HOSTS or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not ip.is_global


def _read_demo_page(url: str, path: str, max_bytes: int) -> FetchedPage:
    name = path[len("/demo/"):]
    folder, _, filename = name.rpartition("/")
    if folder not in DEMO_SUBFOLDERS or not DEMO_FILE_RE.fullmatch(filename):
        return FetchedPage(url=url, status=400, error="Rejected demo page path: only a plain .html file name is allowed.")
    base = DEMO_PAGES_DIR.resolve()
    target = (base / name).resolve()
    expected_parent = (base / folder).resolve() if folder else base
    if target.parent != expected_parent:
        return FetchedPage(url=url, status=400, error="Rejected demo page path.")
    try:
        with target.open("rb") as fh:
            data = fh.read(max_bytes)
    except FileNotFoundError:
        return FetchedPage(url=url, final_url=url, status=404, error=f"Demo page not found: {name}")
    except OSError as exc:
        return FetchedPage(url=url, final_url=url, error=f"Could not read demo page: {type(exc).__name__}")
    return FetchedPage(
        url=url,
        final_url=url,
        status=200,
        content_type="text/html; charset=utf-8",
        html=data.decode("utf-8", errors="replace"),
    )


async def _block_private(request: httpx.Request) -> None:
    if _is_private_host(request.url.host or ""):
        raise _BlockedHost(f"Blocked request to a private or local host: {request.url.host}")
    # Redirect hops also get the full URL policy, including names that resolve to private addresses.
    ok, reason = await asyncio.to_thread(check_url, str(request.url))
    if not ok:
        raise _BlockedHost(f"Blocked request: {reason}")


async def _fetch_remote(url: str, timeout: float, max_bytes: int) -> FetchedPage:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
        "Accept-Language": "en-US,en;q=0.9",
    }
    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
        event_hooks={"request": [_block_private]},
    ) as client:
        async with client.stream("GET", url) as resp:
            final_url = str(resp.url)
            content_type = resp.headers.get("content-type", "")
            mime = content_type.split(";")[0].strip().lower()
            page = FetchedPage(url=url, final_url=final_url, status=resp.status_code, content_type=content_type or None)
            if resp.status_code >= 400:
                page.error = f"HTTP {resp.status_code}"
                return page
            if mime not in ALLOWED_CONTENT_TYPES:
                page.error = f"Unsupported content type: {mime or 'unknown'}"
                return page
            chunks: list[bytes] = []
            size = 0
            async for chunk in resp.aiter_bytes():
                chunks.append(chunk)
                size += len(chunk)
                if size >= max_bytes:
                    break
            body = b"".join(chunks)[:max_bytes]
            page.html = body.decode(resp.encoding or "utf-8", errors="replace")
            return page


async def fetch_url(url: str, timeout: float = 15.0, max_bytes: int = 2_000_000) -> FetchedPage:
    """Fetch HTML. Never raise: put the problem in FetchedPage.error."""
    url = (url or "").strip()
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or not host:
            return FetchedPage(url=url, error="Only http and https URLs can be fetched.")
        max_bytes = max(1, int(max_bytes))
        if _is_local_host(host):
            if parts.path.startswith("/demo/"):
                return _read_demo_page(url, parts.path, max_bytes)
            return FetchedPage(url=url, error="Only /demo/ pages can be fetched from a local host.")
        if offline_mode():
            return FetchedPage(url=url, error="OFFLINE_MODE=1: only local /demo/ pages can be fetched.")
        return await asyncio.wait_for(_fetch_remote(url, float(timeout), max_bytes), timeout=float(timeout) + 5)
    except _BlockedHost as exc:
        return FetchedPage(url=url, error=str(exc))
    except asyncio.TimeoutError:
        return FetchedPage(url=url, error=f"Timed out after {timeout:.0f} s")
    except httpx.TooManyRedirects:
        return FetchedPage(url=url, error=f"More than {MAX_REDIRECTS} redirects")
    except httpx.HTTPError as exc:
        return FetchedPage(url=url, error=f"{type(exc).__name__}: {exc}"[:300])
    except Exception as exc:  # noqa: BLE001 - never raise by contract
        return FetchedPage(url=url, error=f"{type(exc).__name__}: {exc}"[:300])
