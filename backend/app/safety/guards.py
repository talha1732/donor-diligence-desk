"""Input guards, URL policy, and rate limiting (owner: safety and cost builder)."""

from __future__ import annotations

import ipaddress
import posixpath
import re
import socket
import threading
import time
import unicodedata
from collections import deque
from typing import Callable
from urllib.parse import unquote, urlsplit

from app.safety.injection import detect_injection
from app.schemas import DiligenceRequest, SecurityEvent

# --------------------------------------------------------------------------- donor note

_ZERO_WIDTH_RE = re.compile("[­​-‏‪-‮⁠-⁯﻿]")


def _clean_note(note: str) -> str:
    """Drop control characters (keep newline and tab), zero-width and bidi characters."""
    note = _ZERO_WIDTH_RE.sub("", note or "")
    kept = [ch for ch in note if ch in "\n\t" or unicodedata.category(ch) not in ("Cc", "Cf")]
    return "".join(kept).strip()


def screen_request(req: DiligenceRequest) -> tuple[DiligenceRequest, list[SecurityEvent]]:
    """Return a cleaned copy of the request plus security events.
    If donor_note contains instructions aimed at the AI, drop the note (do not fail the run) and emit
    an input_blocked event with severity "warning".

    Also drops any charity website_url that fails the URL policy (checked without DNS here; the
    impact agent's read_page runs the full check_url again) and emits a url_blocked event."""
    events: list[SecurityEvent] = []
    note = _clean_note(req.donor_note)
    findings = detect_injection(note, "user_input") if note else []
    if findings:
        patterns = sorted({f.pattern for f in findings})
        events.append(
            SecurityEvent(
                kind="input_blocked",
                severity="warning",
                detail=(
                    "Donor note was not used because it contains instructions aimed at the AI "
                    f"({', '.join(patterns)}). The run continues without the note."
                ),
                snippet=findings[0].snippet,
            )
        )
        note = ""

    charities = []
    for c in req.charities:
        if c.website_url:
            ok, reason = check_url(c.website_url, resolve=False)
            if not ok:
                events.append(
                    SecurityEvent(
                        kind="url_blocked",
                        severity="blocked",
                        ein=c.ein,
                        detail=f"Website URL was not used: {reason}",
                        snippet=c.website_url[:200],
                    )
                )
                c = c.model_copy(update={"website_url": None})
        charities.append(c)

    cleaned = req.model_copy(update={"donor_note": note, "charities": charities})
    return cleaned, events


# --------------------------------------------------------------------------- URL policy

_BLOCKED_HOSTS = {
    "localhost",
    "metadata",
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254",
    "0.0.0.0",
}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".home.arpa", ".lan", ".intranet", ".corp")
_DEMO_HOSTS = {"127.0.0.1", "localhost"}
_NUMERIC_PART = re.compile(r"^(?:0x[0-9a-f]*|\d+)$", re.IGNORECASE)
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_METADATA_IPS = {"169.254.169.254", "169.254.170.2", "fd00:ec2::254", "100.100.100.200"}


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse an IP literal, including the shorthand forms browsers and libc accept
    (decimal 2130706433, octal 0177.0.0.1, hex 0x7f.1, short 127.1)."""
    try:
        return ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        pass
    if _looks_numeric(host):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(host))
        except OSError:
            return None
    return None


def _looks_numeric(host: str) -> bool:
    parts = host.split(".")
    return bool(parts) and all(p and _NUMERIC_PART.match(p) for p in parts)


def _ip_block_reason(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped or (ip.sixtofour if ip.sixtofour else None)
        if embedded is None and ip.teredo:
            embedded = ip.teredo[1]
        if embedded is None and ip in _NAT64:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if embedded is not None:
            inner = _ip_block_reason(embedded)
            if inner:
                return f"{inner} (embedded in IPv6 address {ip})"
    if str(ip) in _METADATA_IPS:
        return f"cloud metadata address {ip}"
    for attr, label in (
        ("is_loopback", "loopback"),
        ("is_unspecified", "unspecified"),
        ("is_link_local", "link-local"),
        ("is_multicast", "multicast"),
        ("is_private", "private network"),
        ("is_reserved", "reserved"),
    ):
        if getattr(ip, attr, False):
            return f"{label} address {ip}"
    if not ip.is_global:
        return f"non-public address {ip}"
    return None


def _host_block_reason(host: str) -> str | None:
    if host in _BLOCKED_HOSTS:
        return f"internal host name {host}"
    if host.endswith(_BLOCKED_SUFFIXES):
        return f"internal host name {host}"
    if "." not in host:
        return f"single-label host name {host} (resolves on the local network)"
    return None


def _demo_path_ok(path: str) -> bool:
    decoded = unquote(unquote(path or "/"))
    if "\\" in decoded or "\x00" in decoded:
        return False
    if any(seg == ".." for seg in decoded.split("/")):
        return False
    return posixpath.normpath(decoded).startswith("/demo/") and decoded.startswith("/demo/")


def check_url(url: str, *, resolve: bool = True) -> tuple[bool, str]:
    """Allow only http(s) to public hosts. Block private, loopback, link-local and metadata IPs,
    file:// and other schemes. Exception: 127.0.0.1/localhost with a path under /demo/ is allowed.

    With resolve=True the host name is resolved and blocked if any address is non-public. If DNS fails
    the URL is allowed (the fetch will fail anyway). Returns (ok, reason)."""
    if not isinstance(url, str) or not url.strip():
        return False, "empty URL"
    url = url.strip()
    if len(url) > 2000:
        return False, "URL is too long"
    if any(ord(ch) < 33 or ch == "\x7f" for ch in url) or "\\" in url:
        return False, "URL contains whitespace, control characters, or backslashes"
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        return False, f"URL could not be parsed ({exc})"
    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, f"scheme '{scheme or 'none'}' is not allowed (http and https only)"
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return False, "URLs with embedded credentials are not allowed"
    host = (parts.hostname or "").strip().rstrip(".").lower()
    if not host:
        return False, "URL has no host"
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return False, f"host name {host!r} is not valid"

    if host in _DEMO_HOSTS and _demo_path_ok(parts.path):
        return True, "local demo page"

    ip = _parse_ip(host)
    if ip is None and _looks_numeric(host):
        return False, f"blocked numeric host {host} that is not a valid public IP address"
    if ip is not None:
        reason = _ip_block_reason(ip)
        if reason:
            return False, f"blocked {reason}"
        return True, "public IP address"

    reason = _host_block_reason(host)
    if reason:
        return False, f"blocked {reason}"

    if resolve:
        try:
            infos = socket.getaddrinfo(host, port or (443 if scheme == "https" else 80), proto=socket.IPPROTO_TCP)
        except (OSError, UnicodeError):
            return True, "public host (DNS lookup failed; the fetch will fail if the host does not exist)"
        for info in infos:
            try:
                addr = ipaddress.ip_address(str(info[4][0]).split("%", 1)[0])
            except (ValueError, IndexError):
                continue
            reason = _ip_block_reason(addr)
            if reason:
                return False, f"blocked: {host} resolves to {reason}"
    return True, "public host"


# --------------------------------------------------------------------------- rate limiting


class RateLimiter:
    """Sliding-window limiter keyed by client id (IP)."""

    def __init__(
        self,
        max_per_minute: int = 5,
        *,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_per_minute = max_per_minute
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """True if allowed (and records the hit), False if over the limit."""
        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.max_per_minute:
                return False
            hits.append(now)
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
                    del self._hits[k]
            return True

    def retry_after(self, key: str) -> float:
        """Seconds until the oldest hit in the window expires (0 if a request would be allowed now)."""
        now = self._clock()
        with self._lock:
            hits = self._hits.get(key)
            if not hits or len(hits) < self.max_per_minute:
                return 0.0
            return max(0.0, hits[0] + self.window_seconds - now)
