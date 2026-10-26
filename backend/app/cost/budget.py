"""Per-run budget kill switch and global daily cap (owner: safety and cost builder)."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import date
from pathlib import Path

from app.cost.pricing import cost_usd
from app.schemas import AgentUsage, RunUsage

REPO_ROOT = Path(__file__).resolve().parents[3]
_DAILY_LOCK = threading.Lock()
_KEEP_DAYS = 90


class BudgetExceeded(Exception):
    pass


class BudgetTracker:
    """Accumulates usage per agent key during one run. record() raises BudgetExceeded once the run's
    total cost reaches budget_usd (after recording, so the spend is still reported)."""

    def __init__(self, budget_usd: float, model: str) -> None:
        self.budget_usd = budget_usd
        self.model = model
        self._agents: dict[str, AgentUsage] = {}
        self._lock = threading.Lock()
        self.exceeded = False

    def record(
        self,
        agent: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        cache_write_tokens: int = 0,
        requests: int = 1,
        tool_calls: int = 0,
        seconds: float = 0.0,
    ) -> None:
        cost = cost_usd(self.model, input_tokens, output_tokens, cached_tokens, cache_write_tokens)
        with self._lock:
            u = self._agents.get(agent)
            if u is None:
                u = self._agents[agent] = AgentUsage(agent=agent)
            u.requests += int(requests or 0)
            u.input_tokens += int(input_tokens or 0)
            u.cached_tokens += int(cached_tokens or 0)
            u.cache_write_tokens += int(cache_write_tokens or 0)
            u.output_tokens += int(output_tokens or 0)
            u.tool_calls += int(tool_calls or 0)
            u.cost_usd += cost
            u.seconds += float(seconds or 0.0)
            total = self._total_locked()
            if total >= self.budget_usd:
                self.exceeded = True
        if total >= self.budget_usd:
            raise BudgetExceeded(
                f"Run budget of ${self.budget_usd:.2f} reached (spent ${total:.4f}); remaining agents are stopped."
            )

    def _total_locked(self) -> float:
        return sum(u.cost_usd for u in self._agents.values())

    @property
    def total_usd(self) -> float:
        with self._lock:
            return self._total_locked()

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.budget_usd - self.total_usd)

    def agent_usage(self, agent: str) -> AgentUsage:
        with self._lock:
            u = self._agents.get(agent)
            return u.model_copy() if u is not None else AgentUsage(agent=agent)

    def snapshot(self, stopped_by_budget: bool = False) -> RunUsage:
        with self._lock:
            agents = [u.model_copy() for u in self._agents.values()]
        total = AgentUsage(agent="total")
        for u in agents:
            total.requests += u.requests
            total.input_tokens += u.input_tokens
            total.cached_tokens += u.cached_tokens
            total.cache_write_tokens += u.cache_write_tokens
            total.output_tokens += u.output_tokens
            total.tool_calls += u.tool_calls
            total.cost_usd += u.cost_usd
            total.seconds += u.seconds
        return RunUsage(
            model=self.model,
            agents=agents,
            total=total,
            budget_usd=self.budget_usd,
            stopped_by_budget=stopped_by_budget or self.exceeded,
        )


def _output_dir() -> Path:
    return Path(os.environ.get("OUTPUT_DIR") or (REPO_ROOT / "output"))


class DailyBudget:
    """File-backed daily spend cap across all runs (output/daily_spend.json, keyed by ISO date).
    Limit from DAILY_BUDGET_USD (default 2.00). The day is the server's local calendar date.
    Paths and limits are resolved at call time so tests can point OUTPUT_DIR at a temp dir."""

    def __init__(self, limit_usd: float | None = None, path: str | None = None) -> None:
        self.limit_usd = limit_usd
        self.path = path

    def _path(self) -> Path:
        return Path(self.path) if self.path else _output_dir() / "daily_spend.json"

    def _limit(self) -> float:
        if self.limit_usd is not None:
            return float(self.limit_usd)
        try:
            return float(os.environ.get("DAILY_BUDGET_USD") or 2.00)
        except ValueError:
            return 2.00

    def _read(self) -> dict[str, float]:
        try:
            data = json.loads(self._path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        out: dict[str, float] = {}
        for k, v in data.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        return out

    def _write(self, data: dict[str, float]) -> None:
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        keep = dict(sorted(data.items())[-_KEEP_DAYS:])
        fd, tmp = tempfile.mkstemp(prefix=".daily_spend.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(keep, fh, indent=2, sort_keys=True)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @staticmethod
    def _today() -> str:
        return date.today().isoformat()

    def spent_today(self) -> float:
        with _DAILY_LOCK:
            return self._read().get(self._today(), 0.0)

    def remaining(self) -> float:
        return max(0.0, self._limit() - self.spent_today())

    def can_start(self, reserve_usd: float) -> bool:
        """True if a run that may spend up to reserve_usd fits in what is left today."""
        return self.spent_today() + max(0.0, float(reserve_usd or 0.0)) <= self._limit() + 1e-9

    def add(self, cost_usd: float) -> None:
        if not cost_usd or cost_usd <= 0:
            return
        with _DAILY_LOCK:
            data = self._read()
            today = self._today()
            data[today] = round(data.get(today, 0.0) + float(cost_usd), 8)
            self._write(data)
