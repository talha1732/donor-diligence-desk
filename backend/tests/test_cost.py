"""Cost controls and audit trail: pricing math, per-run kill switch, daily cap, run storage. Offline."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from app import audit
from app.cost.budget import BudgetExceeded, BudgetTracker, DailyBudget
from app.cost.pricing import FALLBACK_MODEL, MODEL_PRICES, cost_usd, prices_for, usage_from_pydantic
from app.schemas import (
    AgentUsage,
    CharityInput,
    CharityScorecard,
    DiligenceRequest,
    DiligenceResult,
    GivingMemo,
    OrgSearchResult,
    RunUsage,
    SecurityEvent,
)

# =========================================================================== pricing


def test_cost_hand_computed_example():
    # 10,000 input tokens of which 6,000 cached and 1,000 cache-write; 2,000 output tokens.
    # uncached 3,000 x $0.10/M = $0.000300
    # cached   6,000 x $0.01/M = $0.000060
    # write    1,000 x $0.125/M = $0.000125
    # output   2,000 x $0.50/M = $0.001000
    # total                     = $0.001485
    assert cost_usd("gpt-6-luna", 10_000, 2_000, cached_tokens=6_000, cache_write_tokens=1_000) == pytest.approx(0.001485)


def test_cost_simple_and_floor():
    assert cost_usd("gpt-6-luna", 1_000_000, 0) == pytest.approx(0.10)
    assert cost_usd("gpt-6-luna", 0, 1_000_000) == pytest.approx(0.50)
    # Inconsistent counts never produce a negative uncached part.
    assert cost_usd("gpt-6-luna", 100, 0, cached_tokens=200) == pytest.approx(200 * 0.01 / 1e6)
    assert cost_usd("gpt-6-luna", 0, 0) == 0


def test_unknown_model_falls_back_to_luna_prices():
    assert FALLBACK_MODEL == "gpt-6-luna"
    assert prices_for("openai:gpt-6-luna") == MODEL_PRICES["gpt-6-luna"]
    assert prices_for("gpt-6-luna-2026-09-01") == MODEL_PRICES["gpt-6-luna"]
    assert cost_usd("some-other-model", 1_000_000, 0) == cost_usd("gpt-6-luna", 1_000_000, 0)


def test_usage_from_pydantic_run_usage():
    from pydantic_ai.usage import RequestUsage, RunUsage as PaiRunUsage

    run = PaiRunUsage(requests=3, tool_calls=2, input_tokens=10_000, cache_read_tokens=6_000,
                      cache_write_tokens=1_000, output_tokens=2_000)
    u = usage_from_pydantic(run, model="gpt-6-luna", agent="financial:000000001", seconds=4.5)
    assert isinstance(u, AgentUsage)
    assert (u.requests, u.tool_calls, u.input_tokens, u.cached_tokens, u.cache_write_tokens, u.output_tokens) == (
        3, 2, 10_000, 6_000, 1_000, 2_000)
    assert u.cost_usd == pytest.approx(0.001485)
    assert u.seconds == 4.5 and u.agent == "financial:000000001"

    req = RequestUsage(input_tokens=500, output_tokens=100)
    r = usage_from_pydantic(req, model="gpt-6-luna", agent="memo")
    assert r.requests == 1 and r.tool_calls == 0 and r.input_tokens == 500


def test_usage_from_pydantic_is_defensive():
    class Odd:
        input_tokens = None
        output_tokens = "12"
        details = {"cached_tokens": 5}

    u = usage_from_pydantic(Odd(), model="gpt-6-luna", agent="x")
    assert (u.input_tokens, u.output_tokens, u.cached_tokens, u.requests) == (0, 12, 5, 0)
    assert usage_from_pydantic(None, model="gpt-6-luna", agent="x").cost_usd == 0
    assert usage_from_pydantic({"input_tokens": 1000}, model="gpt-6-luna", agent="x").input_tokens == 1000


# =========================================================================== per-run budget


def test_budget_tracker_stops_at_budget():
    tracker = BudgetTracker(budget_usd=0.01, model="gpt-6-luna")
    # Each call costs 20,000 x 0.10/M + 10,000 x 0.50/M = $0.007.
    tracker.record("financial:000000001", input_tokens=20_000, output_tokens=10_000, tool_calls=2)
    assert tracker.total_usd == pytest.approx(0.007)
    with pytest.raises(BudgetExceeded):
        tracker.record("impact:000000001", input_tokens=20_000, output_tokens=10_000)
    # The spend that crossed the line is still reported.
    snap = tracker.snapshot()
    assert isinstance(snap, RunUsage)
    assert snap.stopped_by_budget is True
    assert snap.total.cost_usd == pytest.approx(0.014)
    assert snap.total.requests == 2 and snap.total.tool_calls == 2
    assert [a.agent for a in snap.agents] == ["financial:000000001", "impact:000000001"]
    assert snap.budget_usd == 0.01 and snap.model == "gpt-6-luna"


def test_budget_tracker_accumulates_per_agent():
    tracker = BudgetTracker(budget_usd=0.10, model="gpt-6-luna")
    for _ in range(3):
        tracker.record("auditor", input_tokens=2_000, cached_tokens=1_024, output_tokens=300, seconds=1.0)
    u = tracker.agent_usage("auditor")
    assert (u.requests, u.input_tokens, u.cached_tokens, u.output_tokens, u.seconds) == (3, 6_000, 3_072, 900, 3.0)
    assert u.cost_usd == pytest.approx(cost_usd("gpt-6-luna", 6_000, 900, 3_072))
    assert tracker.agent_usage("nobody").cost_usd == 0
    snap = tracker.snapshot()
    assert snap.stopped_by_budget is False and snap.total.cost_usd == pytest.approx(u.cost_usd)


def test_budget_tracker_thread_safe():
    tracker = BudgetTracker(budget_usd=100.0, model="gpt-6-luna")

    def worker():
        for _ in range(200):
            tracker.record("a", input_tokens=10, output_tokens=10)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert tracker.agent_usage("a").requests == 1600


# =========================================================================== daily budget


def test_daily_budget_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("DAILY_BUDGET_USD", "0.25")
    day = DailyBudget()
    assert day.spent_today() == 0 and day.remaining() == pytest.approx(0.25)
    assert day.can_start(0.10)
    day.add(0.10)
    day.add(0.08)
    again = DailyBudget()  # a new instance reads the same file
    assert again.spent_today() == pytest.approx(0.18)
    assert again.remaining() == pytest.approx(0.07)
    assert not again.can_start(0.10)
    assert again.can_start(0.05)
    path = Path(os.environ["OUTPUT_DIR"]) / "daily_spend.json"
    data = json.loads(path.read_text())
    assert list(data.values()) == [pytest.approx(0.18)]


def test_daily_budget_explicit_limit_path_and_corrupt_file(tmp_path):
    path = tmp_path / "spend.json"
    path.write_text("{not json")
    day = DailyBudget(limit_usd=1.0, path=str(path))
    assert day.spent_today() == 0
    day.add(0.4)
    assert DailyBudget(limit_usd=1.0, path=str(path)).remaining() == pytest.approx(0.6)
    assert not any(p.name.endswith(".tmp") for p in tmp_path.iterdir())


# =========================================================================== audit trail


@pytest.fixture(autouse=True)
def _no_committed_samples(tmp_path, monkeypatch):
    """Keep committed backend/data/sample_runs out of these tests; one test points it at its own dir."""
    monkeypatch.setattr(audit, "SAMPLE_RUNS_DIR", tmp_path / "no_samples")


def _result(run_id: str, created_at: str = "2026-10-26T05:00:00+00:00") -> DiligenceResult:
    usage = RunUsage(
        model="gpt-6-luna",
        budget_usd=0.10,
        agents=[AgentUsage(agent="memo", requests=1, input_tokens=3000, cached_tokens=1024, output_tokens=400,
                           cost_usd=0.0005)],
        total=AgentUsage(agent="total", requests=1, input_tokens=3000, cached_tokens=1024, output_tokens=400,
                         cost_usd=0.0005),
    )
    return DiligenceResult(
        run_id=run_id,
        created_at=created_at,
        request=DiligenceRequest(charities=[CharityInput(ein="000000001"), CharityInput(ein="000000002")]),
        orgs=[OrgSearchResult(ein="000000001", name="Riverbend Community Pantry (DEMO)", is_demo=True),
              OrgSearchResult(ein="000000002", name="Harbor Lights Literacy Project (DEMO)", is_demo=True)],
        scorecards=[CharityScorecard(ein="000000001", name="Riverbend Community Pantry (DEMO)", overall=61.25,
                                     band="fit_with_questions")],
        memo=GivingMemo(headline="Harbor Lights is the stronger fit.", summary="s", recommendation="r"),
        security_events=[
            SecurityEvent(kind="hidden_text_removed", severity="info", detail="d"),
            SecurityEvent(kind="injection_detected", detail="d"),
            SecurityEvent(kind="injection_detected", detail="d"),
        ],
        usage=usage,
    )


def test_audit_round_trip_with_events():
    result = _result("r-20261026-050000-abc123")
    events = [{"type": "run_started", "ts": "t0", "data": {"run_id": result.run_id}},
              {"type": "final", "ts": "t1", "data": {"ok": True}}]
    record = audit.append_run(result, events)
    out = Path(os.environ["OUTPUT_DIR"])
    assert (out / "runs" / f"{result.run_id}.json").is_file()
    assert (out / "runs" / f"{result.run_id}.events.jsonl").is_file()
    trail = (out / "audit_trail.jsonl").read_text().splitlines()
    assert len(trail) == 1 and json.loads(trail[0]) == record

    assert record["charities"][0] == {"ein": "000000001", "name": "Riverbend Community Pantry (DEMO)",
                                      "band": "fit_with_questions", "overall": 61.2}
    assert record["charities"][1]["ein"] == "000000002" and record["charities"][1]["band"] is None
    assert record["tokens"] == {"input": 3000, "cached": 1024, "cache_write": 0, "output": 400}
    assert record["security_events"] == {"hidden_text_removed": 1, "injection_detected": 2}
    assert record["headline"] == "Harbor Lights is the stronger fit."
    assert record["cost_usd"] == 0.0005 and record["sample"] is False

    loaded = audit.load_run(result.run_id)
    assert loaded is not None and loaded.model_dump() == result.model_dump()
    assert audit.load_events(result.run_id) == events
    assert audit.load_run("r-unknown") is None and audit.load_events("r-unknown") is None


def test_audit_list_runs_newest_first_and_limit():
    audit.append_run(_result("run-a", "2026-10-26T01:00:00+00:00"))
    audit.append_run(_result("run-b", "2026-10-26T03:00:00+00:00"))
    audit.append_run(_result("run-c", "2026-10-26T02:00:00+00:00"))
    assert [r["run_id"] for r in audit.list_runs()] == ["run-b", "run-c", "run-a"]
    assert [r["run_id"] for r in audit.list_runs(limit=1)] == ["run-b"]
    assert audit.load_events("run-a") is None  # no events were passed


def test_audit_reads_sample_runs(tmp_path, monkeypatch):
    sample_dir = tmp_path / "sample_runs"
    sample_dir.mkdir()
    sample = _result("sample-riverbend-harbor", "2026-10-25T20:00:00+00:00")
    (sample_dir / f"{sample.run_id}.json").write_text(sample.model_dump_json())
    (sample_dir / f"{sample.run_id}.events.jsonl").write_text('{"type": "final", "ts": "t", "data": {}}\n')
    (sample_dir / "broken.json").write_text("{not valid")
    monkeypatch.setattr(audit, "SAMPLE_RUNS_DIR", sample_dir)

    audit.append_run(_result("live-run", "2026-10-26T06:00:00+00:00"))
    runs = audit.list_runs()
    assert [(r["run_id"], r["sample"]) for r in runs] == [("live-run", False), ("sample-riverbend-harbor", True)]
    assert audit.load_run("sample-riverbend-harbor").run_id == "sample-riverbend-harbor"
    assert audit.load_events("sample-riverbend-harbor") == [{"type": "final", "ts": "t", "data": {}}]


def test_audit_missing_sample_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "SAMPLE_RUNS_DIR", tmp_path / "does-not-exist")
    assert audit.list_runs() == []


@pytest.mark.parametrize(
    "run_id",
    ["../secrets", "..", "a/b", "a\\b", "/etc/passwd", "run.json", "", " run", "run\n", "%2e%2e", "x" * 81, None],
)
def test_audit_rejects_unsafe_run_ids(run_id):
    assert audit.load_run(run_id) is None
    assert audit.load_events(run_id) is None


def test_audit_append_rejects_unsafe_run_id():
    with pytest.raises(ValueError):
        audit.append_run(_result("../escape"))
    assert not (Path(os.environ["OUTPUT_DIR"]).parent / "escape.json").exists()


def test_audit_skips_corrupt_trail_lines():
    audit.append_run(_result("good-run"))
    trail = Path(os.environ["OUTPUT_DIR"]) / "audit_trail.jsonl"
    with open(trail, "a", encoding="utf-8") as fh:
        fh.write("{truncated line\n")
        fh.write('{"run_id": "../bad"}\n')
    assert [r["run_id"] for r in audit.list_runs()] == ["good-run"]
