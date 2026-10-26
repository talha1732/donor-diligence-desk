"""Claim verifier: every number in a claim must match the evidence ledger (owner: safety and cost builder).

Matching rules are in docs/contract.md section 6. Choices the contract leaves open:
- A number without an explicit sign is compared by absolute value ("revenue fell 12%" matches a
  change of -0.12). A number written with a sign ("-3.2%", "+$40K") must match the signed value.
- Web excerpts and donor input carry numbers in their text, not in `value`. For evidence of kind
  web_excerpt or user_input the numbers in `excerpt` are extracted and matched like-for-like.
- Status precedence: no_numbers, then verified, then unknown_evidence_id, then missing_evidence
  (numbers, no cited ids, and nothing matched anywhere), then unverified_number.
- VerificationReport.verified_count counts status "verified"; flagged_count counts
  unverified_number, unknown_evidence_id and missing_evidence. no_numbers is in neither count.
"""

from __future__ import annotations

import math
import re

from app.schemas import ClaimCheck, Evidence, Finding, VerificationReport

FLAGGED_STATUSES = ("unverified_number", "unknown_evidence_id", "missing_evidence")

# --------------------------------------------------------------------------- extraction

_EVIDENCE_ID = re.compile(r"\b(?:PP|CALC|WEB|USER)-[A-Za-z0-9_.\-]*[A-Za-z0-9_]")

_NOT_QUANTITIES = [
    re.compile(r"\b501\s?\(?\s?c\s?\)?\s?\(?\s?\d{1,2}\s?\)?", re.IGNORECASE),  # 501(c)(3)
    re.compile(r"\b(?:Form\s+)?990(?:[-\s]?(?:EZ|PF|N|T)\b|s\b)", re.IGNORECASE),  # Form 990-EZ, 990s
    re.compile(r"\bForm\s+990\b", re.IGNORECASE),
    re.compile(r"\bEIN[:#\s]*\d{2}-?\d{7}\b", re.IGNORECASE),
    re.compile(r"\b\d{2}-\d{7}\b"),  # EIN with dash
    re.compile(r"\b(?:FY\s?)?(?:199\d|20[0-3]\d)\s?(?:-|–|/)\s?(?:\d{4}|\d{2})\b", re.IGNORECASE),  # 2023-24
    re.compile(r"\b\d{1,2}(?::\d{2})?\s?(?:a\.?m\.?|p\.?m\.?)(?![A-Za-z])", re.IGNORECASE),  # 10 am
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),  # dates
    re.compile(r"\(?\b\d{3}\)?[\s.-]\d{3}[-.]\d{4}\b"),  # phone numbers
    re.compile(r"\b24/7\b"),
    re.compile(r"(?<=\d)\s?/\s?100\b(?![.,]\d)"),  # the "/100" of a 0-100 score
    re.compile(r"\bout\s+of\s+100\b(?![.,]\d)", re.IGNORECASE),
]

_NUM_RE = re.compile(
    r"""
    (?<![\w.$€£])                    # not glued to a word, a decimal point, or a currency sign
    (?<![A-Za-z]-)                             # not K-12, COVID-19
    (?P<sign>[-−+])?
    (?P<cur>\$|US\$)?
    (?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)
    (?:
        (?P<scale1>[KkMmBbTt])(?![A-Za-z])
      | \s?(?P<scale2>trillion|billion|million|thousand|bn|mn|mm)\b
    )?
    (?P<suffix>
        \s?%
      | \s?(?:percent|per\s?cent)(?![A-Za-z])
      | \s?(?:percentage\s+points?|pp|ppts?)(?![A-Za-z])
      | [\s-]?(?:months?|mos?\.?)(?![A-Za-z])
      | [\s-]?(?:years?|yrs?\.?)(?![A-Za-z])
      | \s?(?:dollars|usd)(?![A-Za-z])
    )?
    (?![A-Za-z0-9]|[.,]\d)
    """,
    re.VERBOSE | re.IGNORECASE,
)

_SCALES = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "million": 1e6, "mn": 1e6, "mm": 1e6,
    "b": 1e9, "billion": 1e9, "bn": 1e9,
    "t": 1e12, "trillion": 1e12,
}


_COUNT_NOUN = re.compile(r"\s+(?:filings?|returns?|tax\s+years?|years\s+of\s+filings)\b", re.IGNORECASE)


def _prepare(text: str) -> str:
    text = _EVIDENCE_ID.sub(" ", text or "")
    for pat in _NOT_QUANTITIES:
        text = pat.sub(" ", text)
    return text


def extract_numbers(text: str) -> list[dict]:
    """Return [{raw, value, kind}] where kind is "usd", "percent", "months", "years", "count" or "number".
    "$3.2 million" -> 3_200_000 usd; "12.4%" -> 0.124 percent; "7 months" -> 7 months.

    Each dict also has `signed` (an explicit + or - was written) and `half_step` (half a unit of the
    last digit shown, in the same units as value). Years 1990-2035 written as plain numbers are skipped."""
    out: list[dict] = []
    prepared = _prepare(text)
    for m in _NUM_RE.finditer(prepared):
        num_s = m.group("num")
        try:
            num = float(num_s.replace(",", ""))
        except ValueError:
            continue
        decimals = len(num_s.split(".", 1)[1]) if "." in num_s else 0
        unit_step = 10.0 ** (-decimals)
        scale_key = (m.group("scale1") or m.group("scale2") or "").lower()
        scale = _SCALES.get(scale_key, 1.0)
        suffix = re.sub(r"[\s.\-]", "", (m.group("suffix") or "").lower())
        sign_s = m.group("sign")
        sign = -1.0 if sign_s in ("-", "−") else 1.0
        cur = bool(m.group("cur"))

        if suffix.startswith(("%", "per", "pp")):
            kind, value, half = "percent", num / 100.0, unit_step / 200.0
        elif cur or suffix in ("dollars", "usd"):
            kind, value, half = "usd", num * scale, unit_step * scale / 2.0
        elif suffix.startswith("mo"):
            kind, value, half = "months", num, unit_step / 2.0
        elif suffix.startswith(("year", "yr")):
            kind, value, half = "years", num, unit_step / 2.0
        elif not suffix and not scale_key and _COUNT_NOUN.match(prepared, m.end()):
            kind, value, half = "count", num, unit_step / 2.0
        else:
            kind, value, half = "number", num * scale, unit_step * scale / 2.0
            if not scale_key and decimals == 0 and "," not in num_s and 1990 <= num <= 2035:
                continue  # a year
        out.append(
            {
                "raw": m.group(0).strip(),
                "value": sign * value,
                "kind": kind,
                "signed": sign_s is not None,
                "half_step": half,
            }
        )
    return out


# --------------------------------------------------------------------------- matching


def _close(c: float, e: float, signed: bool) -> tuple[float, float]:
    if not signed:
        c, e = abs(c), abs(e)
    return c, e


def _usd_match(c: float, e: float, half: float, signed: bool) -> bool:
    c, e = _close(c, e, signed)
    diff = abs(c - e)
    if diff <= half + 1e-9:
        return True
    return e != 0 and diff / abs(e) <= 0.02 + 1e-12


def _pct_match(c: float, e: float, half: float, signed: bool) -> bool:
    c, e = _close(c, e, signed)
    return abs(c - e) <= max(0.005, half) + 1e-9


def _count_match(c: float, e: float, signed: bool) -> bool:
    c, e = _close(c, e, signed)
    return abs(c - e) <= max(0.5, 0.02 * abs(e)) + 1e-9


def _match_value(num: dict, unit: str, value: float) -> bool:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return False
    kind, c, half, signed = num["kind"], num["value"], num["half_step"], num["signed"]
    if kind == "usd":
        return unit == "usd" and _usd_match(c, value, half, signed)
    if kind == "percent":
        return unit == "ratio" and _pct_match(c, value, half, signed)
    if kind == "months":
        return unit == "months" and _count_match(c, value, signed)
    if kind == "years":
        if unit in ("years", "count"):
            return _count_match(c, value, signed)
        if unit == "months":
            return _count_match(c * 12, value, signed)
        return False
    if kind == "count":
        return unit in ("count", "years") and _count_match(c, value, signed)
    # plain number
    if abs(c) >= 1000:
        if unit == "usd":
            return _usd_match(c, value, half, signed)
        if unit == "count":
            return _count_match(c, value, signed)
        return False
    return unit in ("count", "years") and _count_match(c, value, signed)


_TEXT_COMPAT = {
    "usd": ("usd", "number"),
    "percent": ("percent",),
    "months": ("months",),
    "years": ("years", "count", "number"),
    "count": ("count", "number", "years"),
    "number": ("number", "count", "usd", "years"),
}


def _match_quoted(num: dict, quoted: dict) -> bool:
    if quoted["kind"] not in _TEXT_COMPAT.get(num["kind"], ()):
        return False
    if num["kind"] == "usd" and quoted["kind"] == "number" and abs(quoted["value"]) < 1000:
        return False
    if num["kind"] == "number" and quoted["kind"] == "usd" and abs(num["value"]) < 1000:
        return False
    half = max(num["half_step"], quoted["half_step"])
    signed = num["signed"] and quoted["signed"]
    if num["kind"] == "percent":
        c, e = _close(num["value"], quoted["value"], signed)
        return abs(c - e) <= half + 1e-9
    return _usd_match(num["value"], quoted["value"], half, signed)


class _Matcher:
    def __init__(self, evidence: dict[str, Evidence]) -> None:
        self.evidence = evidence
        self._quoted: dict[str, list[dict]] = {}

    def quoted_numbers(self, ev: Evidence) -> list[dict]:
        if ev.id not in self._quoted:
            text = " ".join(t for t in (ev.excerpt, ev.display) if t) if ev.kind in ("web_excerpt", "user_input") else ""
            self._quoted[ev.id] = extract_numbers(text) if text else []
        return self._quoted[ev.id]

    def matches(self, num: dict, ev: Evidence) -> bool:
        if ev.value is not None and ev.unit != "text" and _match_value(num, ev.unit, float(ev.value)):
            return True
        return any(_match_quoted(num, q) for q in self.quoted_numbers(ev))

    def find(self, num: dict, ids: list[str]) -> str | None:
        for eid in ids:
            ev = self.evidence.get(eid)
            if ev is not None and self.matches(num, ev):
                return eid
        return None


def _describe(eid: str, evidence: dict[str, Evidence]) -> str:
    ev = evidence.get(eid)
    return f"{eid} ({ev.display})" if ev is not None and ev.display else eid


def _finding_ein(finding: Finding, evidence: dict[str, Evidence]) -> str | None:
    if finding.ein:
        return finding.ein
    if finding.agent and ":" in finding.agent:
        tail = finding.agent.rsplit(":", 1)[1]
        if re.fullmatch(r"\d{9}", tail):
            return tail
    for eid in finding.evidence_ids:
        ev = evidence.get(eid)
        if ev is not None and ev.ein:
            return ev.ein
    return None


def _join(items: list[str], limit: int = 4) -> str:
    shown = items[:limit]
    more = len(items) - len(shown)
    return "; ".join(shown) + (f"; and {more} more" if more > 0 else "")


def verify_finding(finding: Finding, evidence: dict[str, Evidence]) -> ClaimCheck:
    """Check every number in finding.text against its cited evidence, then against other evidence for
    the same EIN. A match found by that fallback search appends the evidence id to finding.evidence_ids."""
    nums = extract_numbers(finding.text)
    cited = list(finding.evidence_ids)
    unknown = [eid for eid in cited if eid not in evidence]
    known = [eid for eid in cited if eid in evidence]
    raws = [n["raw"] for n in nums]

    if not nums:
        detail = "No numbers to check."
        if unknown:
            detail += f" Cited ids not in the evidence ledger: {', '.join(unknown)}."
        return ClaimCheck(finding_id=finding.id, status="no_numbers", detail=detail)

    matcher = _Matcher(evidence)
    ein = _finding_ein(finding, evidence)
    fallback_ids = [
        eid for eid, ev in evidence.items() if ein and ev.ein == ein and eid not in known
    ]
    matched: list[str] = []
    added: list[str] = []
    unmatched: list[str] = []
    for num in nums:
        eid = matcher.find(num, known)
        if eid is None:
            eid = matcher.find(num, fallback_ids)
            if eid is not None and eid not in finding.evidence_ids:
                finding.evidence_ids.append(eid)
                known.append(eid)
                added.append(eid)
        if eid is None:
            unmatched.append(num["raw"])
        else:
            matched.append(f"{num['raw']} matches {_describe(eid, evidence)}")

    if not unmatched:
        status = "verified"
        detail = f"All {len(nums)} number(s) match the evidence: {_join(matched)}."
        if added:
            detail += f" Found in other evidence for this charity, so these ids were added: {', '.join(added)}."
        if unknown:
            detail += f" Cited ids not in the evidence ledger: {', '.join(unknown)}."
    elif unknown:
        status = "unknown_evidence_id"
        detail = (
            f"Cites evidence ids that are not in the ledger: {', '.join(unknown)}. "
            f"Numbers with no matching evidence: {', '.join(unmatched)}."
        )
    elif not cited and not matched:
        status = "missing_evidence"
        detail = (
            f"Contains numbers ({', '.join(unmatched)}) but cites no evidence, and none of them match "
            f"other evidence for {('EIN ' + ein) if ein else 'this charity'}."
        )
    else:
        status = "unverified_number"
        detail = (
            f"{len(unmatched)} of {len(nums)} number(s) do not match the cited evidence or any other evidence "
            f"for {('EIN ' + ein) if ein else 'this charity'}: {', '.join(unmatched)}."
        )
        if matched:
            detail += f" Matched: {_join(matched, 3)}."
    return ClaimCheck(
        finding_id=finding.id,
        status=status,
        numbers_checked=raws,
        unmatched_numbers=unmatched,
        detail=detail,
    )


def verify_findings(findings: list[Finding], evidence: dict[str, Evidence]) -> VerificationReport:
    checks = [verify_finding(f, evidence) for f in findings]
    return VerificationReport(
        checks=checks,
        verified_count=sum(1 for c in checks if c.status == "verified"),
        flagged_count=sum(1 for c in checks if c.status in FLAGGED_STATUSES),
    )


def verify_text(text: str, evidence: dict[str, Evidence], label: str) -> ClaimCheck:
    """Check free text (memo headline, summary) against ALL evidence in the run. finding_id = label."""
    nums = extract_numbers(text)
    if not nums:
        return ClaimCheck(finding_id=label, status="no_numbers", detail="No numbers to check.")
    matcher = _Matcher(evidence)
    ids = list(evidence)
    matched: list[str] = []
    unmatched: list[str] = []
    for num in nums:
        eid = matcher.find(num, ids)
        if eid is None:
            unmatched.append(num["raw"])
        else:
            matched.append(f"{num['raw']} matches {_describe(eid, evidence)}")
    if not unmatched:
        return ClaimCheck(
            finding_id=label,
            status="verified",
            numbers_checked=[n["raw"] for n in nums],
            detail=f"All {len(nums)} number(s) match the run's evidence: {_join(matched)}.",
        )
    detail = f"{len(unmatched)} of {len(nums)} number(s) match no evidence in this run: {', '.join(unmatched)}."
    if matched:
        detail += f" Matched: {_join(matched, 3)}."
    return ClaimCheck(
        finding_id=label,
        status="unverified_number",
        numbers_checked=[n["raw"] for n in nums],
        unmatched_numbers=unmatched,
        detail=detail,
    )


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[$])")


def remove_unverified_sentences(text: str, evidence: dict[str, Evidence]) -> tuple[str, list[str]]:
    """Drop each sentence of free text whose numbers do not all match the run's evidence.
    Returns (kept_text, removed_sentences). Used with defenses on for memo headline/summary/etc."""
    kept: list[str] = []
    removed: list[str] = []
    for sentence in _SENTENCE_SPLIT.split((text or "").strip()):
        if not sentence:
            continue
        check = verify_text(sentence, evidence, "sentence")
        (removed if check.status == "unverified_number" else kept).append(sentence)
    return " ".join(kept), removed
