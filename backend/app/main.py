"""FastAPI app: API routes, SSE run stream, demo pages and the built UI (owner: agents builder)."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse

from app import audit
from app.config import DEMO_PAGES_DIR, ENV_HELP, FRONTEND_DIST, get_settings
from app.cost import pricing
from app.cost.budget import DailyBudget
from app.events import now_iso, sse_format
from app.orchestrator import run_diligence
from app.safety.guards import RateLimiter
from app.schemas import DiligenceRequest
from app.tools import financials, propublica

log = logging.getLogger("diligence")

RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
DEMO_FILE_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,100}\.(?:html?|css|png|jpe?g|svg|gif|webp|ico)$")
KEEPALIVE_S = 15.0

PLACEHOLDER_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Donor Diligence Desk</title>
<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:60px auto;color:#14213d;line-height:1.5}
h1{font-family:Georgia,serif}code{background:#f2f4f8;padding:2px 4px}</style></head>
<body><h1>Donor Diligence Desk</h1>
<p>The API is running, but the web interface has not been built yet (<code>frontend/dist</code> is missing).</p>
<p>Build it with <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>, then reload this page.</p>
<p>API status: <a href="/api/health">/api/health</a>. Interactive API docs: <a href="/docs">/docs</a>.</p>
</body></html>"""


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _daily_budget(settings) -> DailyBudget:
    return DailyBudget(limit_usd=settings.daily_budget_usd, path=str(settings.output_dir / "daily_spend.json"))


def _error_stream(message: str):
    async def gen():
        event = {"type": "error", "ts": now_iso(), "data": {"message": message, "partial": None}}
        yield sse_format(event)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def create_app(model_override: Any = None) -> FastAPI:
    """model_override lets tests inject a PydanticAI TestModel or FunctionModel."""
    app = FastAPI(title="Donor Diligence Desk", version="1.0")
    app.state.model_override = model_override
    app.state.rate_limiter = None
    app.state.background_runs = set()

    def limiter() -> RateLimiter:
        if app.state.rate_limiter is None:
            app.state.rate_limiter = RateLimiter(max_per_minute=get_settings().rate_limit_per_min)
        return app.state.rate_limiter

    def rate_limited(request: Request) -> bool:
        try:
            return not limiter().check(_client_ip(request))
        except Exception as exc:  # a broken limiter must not block every run
            log.warning("rate limiter failed: %s", exc)
            return False

    def can_run() -> str | None:
        """None if a run may start, otherwise a message explaining why not."""
        if app.state.model_override is None and not get_settings().key_present:
            return ENV_HELP
        return None

    # ------------------------------------------------------------------ API

    @app.get("/api/health")
    async def health() -> dict:
        settings = get_settings()
        try:
            spent = _daily_budget(settings).spent_today()
        except Exception:
            spent = 0.0
        return {
            "ok": True,
            "model": settings.model_name,
            "portkey_key_set": settings.key_present,
            "offline_mode": settings.offline_mode,
            "allow_defense_toggle": settings.allow_defense_toggle,
            "run_budget_usd": settings.run_budget_usd,
            "max_run_budget_usd": settings.max_run_budget_usd,
            "daily_budget_usd": settings.daily_budget_usd,
            "daily_spent_usd": round(spent, 6),
            "frontend_built": (FRONTEND_DIST / "index.html").is_file(),
            "setup_help": None if settings.key_present else ENV_HELP,
        }

    @app.get("/api/search")
    async def search(q: str = "", state: str | None = None) -> dict:
        q = q.strip()[:120]
        if not q:
            return {"results": []}
        try:
            results = await propublica.search_orgs(q, state=state)
        except Exception as exc:
            log.warning("search failed: %s", exc)
            return {"results": [], "error": "Search is unavailable right now; try a featured charity or an EIN."}
        return {"results": [r.model_dump(mode="json") for r in results]}

    @app.get("/api/featured")
    async def featured() -> dict:
        try:
            results = propublica.list_featured_orgs()
        except Exception as exc:
            log.warning("featured failed: %s", exc)
            results = []
        return {"results": [r.model_dump(mode="json") for r in results]}

    @app.get("/api/org/{ein}")
    async def org(ein: str):
        norm = propublica.normalize_ein(ein)
        if not norm:
            return JSONResponse({"detail": "EIN must be 9 digits."}, status_code=400)
        try:
            profile = await propublica.get_org_profile(norm, require_filings=False)
        except propublica.ProPublicaUnavailable as exc:
            return JSONResponse({"detail": str(exc)}, status_code=503)
        except propublica.OrgNotFound as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)
        try:
            irs = financials.build_irs_evidence(profile)
            metrics, calc = financials.compute_metrics(profile)
        except Exception as exc:
            log.warning("metrics failed for %s: %s", norm, exc)
            return {"profile": profile.model_dump(mode="json"), "metrics": None, "evidence": {}}
        evidence = {k: v.model_dump(mode="json") for k, v in {**irs, **calc}.items()}
        return {"profile": profile.model_dump(mode="json"), "metrics": metrics.model_dump(mode="json"), "evidence": evidence}

    @app.post("/api/diligence/stream")
    async def diligence_stream(req: DiligenceRequest, request: Request):
        if rate_limited(request):
            return JSONResponse(
                {"detail": "Too many runs from this address; wait a minute and try again."}, status_code=429
            )
        problem = can_run()
        if problem:
            return _error_stream(problem)

        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(run_diligence(req, queue=queue, model=app.state.model_override))
        app.state.background_runs.add(task)
        task.add_done_callback(app.state.background_runs.discard)

        async def gen():
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_S)
                except asyncio.TimeoutError:
                    if task.done() and queue.empty():
                        break
                    yield ": keepalive\n\n"
                    continue
                if event is None:
                    break
                yield sse_format(event)
            if task.done() and not task.cancelled() and task.exception() is not None:
                err = {"type": "error", "ts": now_iso(), "data": {"message": "The run failed unexpectedly.", "partial": None}}
                yield sse_format(err)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
        )

    @app.post("/api/diligence")
    async def diligence(req: DiligenceRequest, request: Request):
        if rate_limited(request):
            return JSONResponse(
                {"detail": "Too many runs from this address; wait a minute and try again."}, status_code=429
            )
        problem = can_run()
        if problem:
            return JSONResponse({"detail": problem}, status_code=503)
        result = await run_diligence(req, model=app.state.model_override)
        return result.model_dump(mode="json")

    @app.get("/api/pricing")
    async def get_pricing() -> dict:
        settings = get_settings()
        return {
            "model": settings.model_name,
            "prices_per_million": pricing.MODEL_PRICES.get(settings.model_name, {}),
            "source": pricing.PRICING_SOURCE,
        }

    @app.get("/api/runs")
    async def runs() -> dict:
        try:
            return {"runs": audit.list_runs()}
        except Exception as exc:
            log.warning("list_runs failed: %s", exc)
            return {"runs": []}

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str):
        if not RUN_ID_RE.match(run_id) or ".." in run_id:
            return JSONResponse({"detail": "Unknown run."}, status_code=404)
        try:
            result = audit.load_run(run_id)
        except Exception:
            result = None
        if result is None:
            return JSONResponse({"detail": "Unknown run."}, status_code=404)
        return result.model_dump(mode="json")

    @app.get("/api/runs/{run_id}/events")
    async def get_run_events(run_id: str):
        if not RUN_ID_RE.match(run_id) or ".." in run_id:
            return JSONResponse({"detail": "Unknown run."}, status_code=404)
        try:
            events = audit.load_events(run_id)
        except Exception:
            events = None
        if events is None:
            return JSONResponse({"detail": "Unknown run."}, status_code=404)
        return {"events": events}

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def api_not_found(rest: str):
        return JSONResponse({"detail": "Not found."}, status_code=404)

    # ------------------------------------------------------------------ demo pages and UI

    def serve_demo(base: Path, file: str):
        if not DEMO_FILE_RE.match(file) or ".." in file:
            return JSONResponse({"detail": "Not found."}, status_code=404)
        base = base.resolve()
        path = (base / file).resolve()
        if path.parent != base or not path.is_file():
            return JSONResponse({"detail": "Not found."}, status_code=404)
        return FileResponse(path)

    @app.get("/demo/{file}")
    async def demo_page(file: str):
        return serve_demo(DEMO_PAGES_DIR, file)

    @app.get("/demo/attacks/{file}")
    async def demo_attack_page(file: str):
        return serve_demo(DEMO_PAGES_DIR / "attacks", file)

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        if path.startswith(("demo/", "api/")) or ".." in path.split("/"):
            return JSONResponse({"detail": "Not found."}, status_code=404)
        dist = FRONTEND_DIST.resolve()
        index = dist / "index.html"
        if not index.is_file():
            return HTMLResponse(PLACEHOLDER_HTML)
        if path:
            candidate = (dist / path).resolve()
            if candidate.is_file() and dist in candidate.parents:
                return FileResponse(candidate)
            if Path(path).suffix and not path.endswith(".html"):
                return Response(status_code=404)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
