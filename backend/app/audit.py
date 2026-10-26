"""Audit trail (owner: safety and cost builder).

- OUTPUT_DIR/audit_trail.jsonl: one compact line per run (append only, never rewrite earlier lines)
- OUTPUT_DIR/runs/<run_id>.json: the full DiligenceResult, used for token evidence in the report
- OUTPUT_DIR/runs/<run_id>.events.jsonl: every SSE event of the run, in order (contract 12.4)
- backend/data/sample_runs/: committed runs in the same layout, listed with "sample": true so a saved
  memo can be opened even without a working API key.

OUTPUT_DIR is read from the environment at call time (default REPO_ROOT/output).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from app.schemas import DiligenceResult

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_RUNS_DIR = Path(__file__).resolve().parents[1] / "data" / "sample_runs"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")

_LOCK = threading.Lock()


def _output_dir() -> Path:
    return Path(os.environ.get("OUTPUT_DIR") or (REPO_ROOT / "output"))


def _runs_dir() -> Path:
    return _output_dir() / "runs"


def valid_run_id(run_id: Any) -> bool:
    return isinstance(run_id, str) and bool(RUN_ID_RE.fullmatch(run_id))


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def compact_record(result: DiligenceResult, *, sample: bool = False) -> dict:
    """The one-line summary written to audit_trail.jsonl and returned by list_runs."""
    names = {o.ein: o.name for o in result.orgs}
    charities: list[dict] = []
    seen: set[str] = set()
    for sc in result.scorecards:
        charities.append(
            {
                "ein": sc.ein,
                "name": sc.name,
                "band": sc.band,
                "overall": round(sc.overall, 1) if sc.overall is not None else None,
            }
        )
        seen.add(sc.ein)
    for c in result.request.charities:
        if c.ein not in seen:
            charities.append({"ein": c.ein, "name": names.get(c.ein, c.ein), "band": None, "overall": None})
            seen.add(c.ein)
    total = result.usage.total
    kinds = Counter(e.kind for e in result.security_events)
    return {
        "run_id": result.run_id,
        "created_at": result.created_at,
        "status": result.status,
        "defenses_on": result.defenses_on,
        "model": result.usage.model,
        "charities": charities,
        "cost_usd": round(total.cost_usd, 6),
        "budget_usd": result.usage.budget_usd,
        "stopped_by_budget": result.usage.stopped_by_budget,
        "tokens": {
            "input": total.input_tokens,
            "cached": total.cached_tokens,
            "cache_write": total.cache_write_tokens,
            "output": total.output_tokens,
        },
        "requests": total.requests,
        "security_events": dict(sorted(kinds.items())),
        "headline": result.memo.headline if result.memo else None,
        "error": result.error,
        "sample": sample,
    }


def append_run(result: DiligenceResult, events: list[dict] | None = None) -> dict:
    """Write runs/<run_id>.json and runs/<run_id>.events.jsonl, then append the compact line to
    audit_trail.jsonl. Returns the compact record. Raises ValueError for an unsafe run_id."""
    if not valid_run_id(result.run_id):
        raise ValueError(f"run_id must match {RUN_ID_RE.pattern}")
    runs = _runs_dir()
    _atomic_write(runs / f"{result.run_id}.json", result.model_dump_json(indent=2))
    if events is not None:
        lines = [json.dumps(e, ensure_ascii=False, default=str) for e in events]
        _atomic_write(runs / f"{result.run_id}.events.jsonl", "".join(line + "\n" for line in lines))
    record = compact_record(result)
    line = json.dumps(record, ensure_ascii=False, default=str)
    trail = _output_dir() / "audit_trail.jsonl"
    with _LOCK:
        trail.parent.mkdir(parents=True, exist_ok=True)
        with open(trail, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    return record


def _read_trail() -> list[dict]:
    trail = _output_dir() / "audit_trail.jsonl"
    try:
        text = trail.read_text(encoding="utf-8")
    except OSError:
        return []
    records: dict[str, dict] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and valid_run_id(rec.get("run_id")):
            rec.setdefault("sample", False)
            records[rec["run_id"]] = rec
    return list(records.values())


def _sample_records() -> list[dict]:
    if not SAMPLE_RUNS_DIR.is_dir():
        return []
    out: list[dict] = []
    for path in sorted(SAMPLE_RUNS_DIR.glob("*.json")):
        run_id = path.stem
        if not valid_run_id(run_id):
            continue
        try:
            result = DiligenceResult.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append(compact_record(result, sample=True))
    return out


def list_runs(limit: int = 20) -> list[dict]:
    """Newest first, compact records from audit_trail.jsonl plus committed sample runs."""
    records = {r["run_id"]: r for r in _sample_records()}
    records.update({r["run_id"]: r for r in _read_trail()})
    ordered = sorted(records.values(), key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return ordered[: max(0, int(limit))]


def _find(run_id: str, suffix: str) -> Path | None:
    if not valid_run_id(run_id):
        return None
    for base in (_runs_dir(), SAMPLE_RUNS_DIR):
        path = base / f"{run_id}{suffix}"
        if path.is_file():
            return path
    return None


def load_run(run_id: str) -> DiligenceResult | None:
    path = _find(run_id, ".json")
    if path is None:
        return None
    try:
        return DiligenceResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_events(run_id: str) -> list[dict] | None:
    """Events of a run in order, or None if the run has no events file."""
    path = _find(run_id, ".events.jsonl")
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    events: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events
