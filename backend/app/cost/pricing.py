"""Token pricing (owner: safety and cost builder).

OpenAI Standard short-context prices, USD per 1M tokens, as given in MGT 409 Lecture 11
(source: https://developers.openai.com/api/docs/pricing):
  gpt-6-luna: input 0.10, cached input 0.01, cache write 0.125, output 0.50
input_tokens is inclusive of cached and cache-write tokens. Uncached = input - cached - cache_write.
"""

from __future__ import annotations

from typing import Any

from app.schemas import AgentUsage

PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"
MODEL_PRICES: dict[str, dict[str, float]] = {
    "gpt-6-luna": {"input": 0.10, "cached": 0.01, "cache_write": 0.125, "output": 0.50},
}
# A model name that is not in MODEL_PRICES is priced as gpt-6-luna (the only model the course key
# allows). If another model is ever added, put its prices above; the fallback would under-report it.
FALLBACK_MODEL = "gpt-6-luna"


def prices_for(model: str) -> dict[str, float]:
    """Per-1M-token prices for a model name. Accepts provider prefixes ("openai:gpt-6-luna") and
    dated suffixes ("gpt-6-luna-2026-09-01"); anything else falls back to FALLBACK_MODEL."""
    name = (model or "").strip().lower()
    if name in MODEL_PRICES:
        return MODEL_PRICES[name]
    for sep in (":", "/"):
        if sep in name:
            name = name.rsplit(sep, 1)[1]
    if name in MODEL_PRICES:
        return MODEL_PRICES[name]
    for key in sorted(MODEL_PRICES, key=len, reverse=True):
        if name.startswith(key):
            return MODEL_PRICES[key]
    return MODEL_PRICES[FALLBACK_MODEL]


def cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Dollar cost of one or more requests. input_tokens includes cached and cache-write tokens."""
    p = prices_for(model)
    input_tokens = max(0, int(input_tokens or 0))
    cached = max(0, int(cached_tokens or 0))
    cache_write = max(0, int(cache_write_tokens or 0))
    output = max(0, int(output_tokens or 0))
    uncached = max(0, input_tokens - cached - cache_write)
    total = (
        uncached * p["input"]
        + cached * p["cached"]
        + cache_write * p["cache_write"]
        + output * p["output"]
    ) / 1_000_000
    return round(total, 10)


def _get_int(obj: Any, *names: str) -> int:
    for name in names:
        if isinstance(obj, dict):
            value = obj.get(name)
        else:
            try:
                value = getattr(obj, name, None)
            except Exception:  # a property that raises
                value = None
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def usage_from_pydantic(usage: Any, *, model: str, agent: str, seconds: float = 0.0) -> AgentUsage:
    """Convert a PydanticAI RunUsage/RequestUsage (input_tokens, output_tokens, cache_read_tokens,
    cache_write_tokens, requests, tool_calls; any may be missing) into AgentUsage with cost_usd."""
    if usage is None:
        return AgentUsage(agent=agent, seconds=seconds)
    input_tokens = _get_int(usage, "input_tokens", "request_tokens", "prompt_tokens")
    output_tokens = _get_int(usage, "output_tokens", "response_tokens", "completion_tokens")
    cached = _get_int(usage, "cache_read_tokens", "cached_tokens")
    if not cached:
        details = usage.get("details") if isinstance(usage, dict) else getattr(usage, "details", None)
        if isinstance(details, dict):
            cached = _get_int(details, "cached_tokens", "cache_read_tokens")
    cache_write = _get_int(usage, "cache_write_tokens")
    requests = _get_int(usage, "requests")
    tool_calls = _get_int(usage, "tool_calls")
    return AgentUsage(
        agent=agent,
        requests=requests,
        input_tokens=input_tokens,
        cached_tokens=cached,
        cache_write_tokens=cache_write,
        output_tokens=output_tokens,
        tool_calls=tool_calls,
        cost_usd=cost_usd(model, input_tokens, output_tokens, cached, cache_write),
        seconds=seconds,
    )
