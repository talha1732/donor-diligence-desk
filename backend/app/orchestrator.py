"""The diligence run pipeline, contract section 7 (owner: agents builder).

intake (no LLM) -> parallel specialists -> deterministic verification and removal -> auditor ->
deterministic scoring -> memo (assembled from verified findings only, then verify_text) -> audit trail.

run_diligence() never raises for ordinary failures: agent errors become report status "error", a
budget stop returns a partial result with status "stopped_budget", and anything unexpected returns a
partial result with status "error".
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app import audit
from app.agents import auditor as auditor_agent
from app.agents import financial as financial_agent
from app.agents import impact as impact_agent
from app.agents import memo as memo_agent
from app.agents.base import (
    AUDITOR_LIMITS,
    FINANCIAL_LIMITS,
    IMPACT_LIMITS,
    MEMO_LIMITS,
    AgentDeps,
    clean_evidence_ids,
    short,
)
from app.config import ENV_HELP, Settings, build_model, get_settings
from app.cost.budget import BudgetExceeded, BudgetTracker, DailyBudget
from app.events import AgentOutcome, RunSession, now_iso, run_agent
from app.safety import guards, verify
from app.schemas import (
    IMPACT_EVIDENCE_LEVELS,
    AuditReport,
    CharityScorecard,
    CharitySection,
    ClaimCheck,
    DiligenceRequest,
    DiligenceResult,
    Evidence,
    FinancialMetrics,
    Finding,
    GivingMemo,
    ImpactAgentOutput,
    ImpactAssessment,
    MemoAgentOutput,
    OrgProfile,
    OrgSearchResult,
    SecurityEvent,
    SpecialistReport,
    VerificationReport,
)
from app.tools import financials, propublica, scoring

log = logging.getLogger("diligence")

RUN_TIMEOUT_S = 240.0
AGENT_TIMEOUT_S = 90.0
HARD_STOP_GRACE_S = 20.0
MIN_SECONDS_FOR_AUDITOR = 25.0
MIN_SECONDS_FOR_MEMO = 20.0
FLAGGED = {"unverified_number", "missing_evidence", "unknown_evidence_id"}
PROGRAM_QUESTION = (
    "What share of total expenses went to program services in your latest Form 990 (Part IX, column B)?"
)
BAND_WORDS = memo_agent.BAND_WORDS


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"run-{stamp}-{secrets.token_hex(3)}"


def _dedupe(items: list[str], limit: int | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = (item or "").strip()
        key = re.sub(r"\W+", " ", text.lower()).strip()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out[:limit] if limit else out


class DiligenceRun:
    def __init__(
        self,
        req: DiligenceRequest,
        *,
        settings: Settings,
        model: Any = None,
        queue: asyncio.Queue | None = None,
        run_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.original_request = req
        self.req = req
        self.model = model
        self.defenses_on = not (req.defenses_off and settings.allow_defense_toggle)
        requested = req.budget_usd if req.budget_usd is not None else settings.run_budget_usd
        self.budget_usd = round(min(requested, settings.max_run_budget_usd), 4)
        self.created_at = now_iso()
        self.started_monotonic = time.monotonic()
        self.session = RunSession(
            run_id or new_run_id(),
            model_name=settings.model_name,
            budget=BudgetTracker(self.budget_usd, settings.model_name),
            defenses_on=self.defenses_on,
            deadline=time.monotonic() + RUN_TIMEOUT_S,
            queue=queue,
        )
        self.daily = DailyBudget(
            limit_usd=settings.daily_budget_usd, path=str(settings.output_dir / "daily_spend.json")
        )
        self.status = "complete"
        self.errors: list[str] = []
        self.profiles: list[OrgProfile] = []
        self.metrics: dict[str, FinancialMetrics] = {}
        self.reports: dict[str, SpecialistReport] = {}
        self.impacts: dict[str, ImpactAssessment] = {}
        self.verification = VerificationReport()
        self.checks: dict[str, ClaimCheck] = {}
        self.removed: dict[str, str] = {}
        self.auditor_notes: list[str] = []
        self.added_questions: dict[str, list[str]] = {}
        self.audit_ran = False
        self.verified = False
        self.scorecards: dict[str, CharityScorecard] = {}
        self.memo: GivingMemo | None = None
        self.text_checks: list[ClaimCheck] = []

    @property
    def run_id(self) -> str:
        return self.session.run_id

    # ------------------------------------------------------------------ entry

    async def execute(self) -> DiligenceResult:
        try:
            async with asyncio.timeout(RUN_TIMEOUT_S + HARD_STOP_GRACE_S):
                await self._pipeline()
        except BudgetExceeded:
            await self._budget_stop()
        except TimeoutError:
            self._fail(f"The run passed its {RUN_TIMEOUT_S:.0f}-second time limit and was stopped.")
            self._finish_deterministic(partial_reason="The run hit its time limit before the memo was written.")
        except Exception as exc:  # last line of defence: never crash the request
            log.exception("diligence run %s failed", self.run_id)
            self._fail(f"Unexpected error: {type(exc).__name__}: {short(str(exc), 300)}")
            self._finish_deterministic(partial_reason="The run hit an unexpected error before the memo was written.")
        return self._finish()

    async def _pipeline(self) -> None:
        if not await self._intake():
            return
        if self.model is None:
            if not self.settings.key_present:
                self._fail(ENV_HELP)
                return
            self.model = build_model(self.settings)
        await self._research()
        self._verify()
        await self._audit()
        self._score()
        await self._write_memo()
        specialist = [r for r in self.reports.values()]
        if specialist and all(r.status == "error" for r in specialist):
            first = next((r.error for r in specialist if r.error), "all agents failed")
            self._fail(f"Every research agent failed, so the memo uses IRS data only. First error: {first}")

    # ------------------------------------------------------------------ 1. intake

    async def _intake(self) -> bool:
        session = self.session
        screen_events: list[SecurityEvent] = []
        if self.defenses_on:
            try:
                self.req, screen_events = guards.screen_request(self.original_request)
            except Exception as exc:
                log.warning("screen_request failed: %s", exc)
                self.req = self.original_request

        charities = list({c.ein: c for c in reversed(self.req.charities)}.values())[::-1]
        results = await asyncio.gather(
            *(propublica.get_org_profile(c.ein) for c in charities), return_exceptions=True
        )
        for charity, res in zip(charities, results):
            if isinstance(res, BaseException):
                self.errors.append(f"EIN {charity.ein}: {short(str(res), 200) or type(res).__name__}")
                continue
            profile = res
            if charity.website_url:
                profile = profile.model_copy(update={"website_url": charity.website_url})
            self.profiles.append(profile)

        session.emit(
            "run_started",
            {
                "run_id": self.run_id,
                "model": self.settings.model_name,
                "budget_usd": self.budget_usd,
                "defenses_on": self.defenses_on,
                "charities": [{"ein": p.ein, "name": p.name, "is_demo": p.is_demo} for p in self.profiles],
                "weights": self.req.weights,
            },
        )
        session.stage("intake", "started")
        for ev in screen_events:
            session.security(ev)

        if not self.profiles:
            self._fail("None of the charities could be loaded. " + " ".join(self.errors))
            session.stage("intake", "done")
            return False

        try:
            allowed = self.daily.can_start(self.budget_usd)
        except Exception as exc:
            log.warning("daily budget check failed: %s", exc)
            allowed = True
        if not allowed:
            session.security(
                SecurityEvent(
                    kind="daily_budget_stop",
                    severity="blocked",
                    detail=f"The app's daily spending cap (${self.settings.daily_budget_usd:.2f}) has been reached. "
                    "No model calls were made. Try again tomorrow or raise DAILY_BUDGET_USD.",
                )
            )
            self.status = "stopped_budget"
            self.errors.append("Daily budget reached.")

        for profile in self.profiles:
            try:
                irs = financials.build_irs_evidence(profile)
                metrics, calc = financials.compute_metrics(profile)
            except Exception as exc:
                log.exception("financial evidence failed for %s", profile.ein)
                self.errors.append(f"EIN {profile.ein}: financial metrics failed ({type(exc).__name__}).")
                irs, calc = {}, {}
                metrics = FinancialMetrics(ein=profile.ein)
            self.metrics[profile.ein] = metrics
            session.add_evidence({**irs, **calc})

        note = (self.req.donor_note or "").strip()
        if note:
            session.add_evidence(
                [Evidence(id="USER-1", kind="user_input", label="Donor's note", display=short(note, 120), excerpt=note)]
            )
        session.stage("intake", "done")
        return allowed

    # ------------------------------------------------------------------ 2. research

    async def _research(self) -> None:
        self.session.stage("research", "started")
        coros = []
        for profile in self.profiles:
            coros.append(self._financial(profile))
            coros.append(self._impact(profile))
        await self._run_parallel(coros)
        self.session.stage("research", "done")

    async def _run_parallel(self, coros: list) -> None:
        tasks = [asyncio.ensure_future(c) for c in coros]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()
            raise
        failure: BaseException | None = None
        for t in done:
            if not t.cancelled() and t.exception() is not None:
                failure = failure or t.exception()
        if failure is not None:
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            raise failure

    def _agent_timeout(self) -> float:
        return max(1.0, min(AGENT_TIMEOUT_S, self.session.remaining_seconds()))

    def _placeholder(self, key: str, role: str, ein: str) -> None:
        self.reports[key] = SpecialistReport(
            agent=key, role=role, ein=ein, status="stopped", summary="The agent did not finish."  # type: ignore[arg-type]
        )

    def _findings_from(self, key: str, ein: str, drafts: list) -> list[Finding]:
        return [
            Finding(
                id=self.session.next_finding_id(key),
                ein=ein,
                agent=key,
                dimension=d.dimension,
                stance=d.stance,
                text=d.text,
                evidence_ids=clean_evidence_ids(d.evidence_ids),
            )
            for d in drafts
        ]

    def _error_report(self, key: str, role: str, ein: str, outcome: AgentOutcome) -> SpecialistReport:
        return SpecialistReport(
            agent=key,
            role=role,  # type: ignore[arg-type]
            ein=ein,
            status="error",
            summary="The agent did not finish; the memo uses the deterministic IRS data for this charity.",
            error=outcome.error,
        )

    async def _financial(self, profile: OrgProfile) -> None:
        key = f"financial:{profile.ein}"
        self._placeholder(key, "financial", profile.ein)
        deps = AgentDeps(
            session=self.session,
            agent_key=key,
            ein=profile.ein,
            limits=FINANCIAL_LIMITS,
            profile=profile,
            metrics=self.metrics.get(profile.ein),
        )
        outcome = await run_agent(
            self.session,
            agent=financial_agent.agent,
            agent_key=key,
            role=financial_agent.ROLE,
            label=f"{financial_agent.ROLE}: {profile.name}",
            ein=profile.ein,
            prompt=financial_agent.build_prompt(profile, self.metrics.get(profile.ein), self.session.evidence),
            deps=deps,
            usage_limits=FINANCIAL_LIMITS.usage_limits(),
            timeout=self._agent_timeout(),
            model=self.model,
            summarize=financial_agent.summarize,
        )
        if outcome.status != "done":
            self.reports[key] = self._error_report(key, "financial", profile.ein, outcome)
            return
        out = outcome.output
        self.reports[key] = SpecialistReport(
            agent=key,
            role="financial",
            ein=profile.ein,
            status="done",
            summary=out.summary,
            findings=self._findings_from(key, profile.ein, out.findings),
            questions_for_charity=list(out.questions_for_charity),
            could_not_verify=list(out.could_not_verify),
        )

    async def _impact(self, profile: OrgProfile) -> None:
        key = f"impact:{profile.ein}"
        self._placeholder(key, "impact", profile.ein)
        deps = AgentDeps(
            session=self.session,
            agent_key=key,
            ein=profile.ein,
            limits=IMPACT_LIMITS,
            profile=profile,
            website_url=profile.website_url,
        )
        outcome = await run_agent(
            self.session,
            agent=impact_agent.agent,
            agent_key=key,
            role=impact_agent.ROLE,
            label=f"{impact_agent.ROLE}: {profile.name}",
            ein=profile.ein,
            prompt=impact_agent.build_prompt(profile, profile.website_url, self.req.donor_note or ""),
            deps=deps,
            usage_limits=IMPACT_LIMITS.usage_limits(),
            timeout=self._agent_timeout(),
            model=self.model,
            summarize=impact_agent.summarize,
        )
        if outcome.status != "done":
            self.reports[key] = self._error_report(key, "impact", profile.ein, outcome)
            return
        out: ImpactAgentOutput = outcome.output
        assessment = self._impact_assessment(profile, out, deps)
        self.impacts[profile.ein] = assessment
        self.reports[key] = SpecialistReport(
            agent=key,
            role="impact",
            ein=profile.ein,
            status="done",
            summary=out.summary,
            findings=self._findings_from(key, profile.ein, out.findings),
            questions_for_charity=list(out.questions_for_charity),
            could_not_verify=list(out.could_not_verify),
            impact=assessment,
        )

    def _impact_assessment(self, profile: OrgProfile, out: ImpactAgentOutput, deps: AgentDeps) -> ImpactAssessment:
        level = out.evidence_level
        rationale = out.evidence_level_rationale
        read_anything = bool(deps.web_evidence_ids)
        if self.defenses_on:
            if not read_anything and level > 0:
                level = 0
                rationale = (rationale + " (Set to 0: no web content was read in this run.)").strip()
            elif level == 4 and not self._has_independent_source(profile, deps):
                level = 3
                rationale = (rationale + " (Capped at 3: no independent source is in the evidence ledger.)").strip()
        return ImpactAssessment(
            ein=profile.ein,
            website_url=out.website_url or deps.website_url,
            pages_read=list(deps.pages_read),
            evidence_level=level,
            evidence_level_label=IMPACT_EVIDENCE_LEVELS.get(level, ""),
            rationale=rationale,
            publishes_financials=out.publishes_financials if deps.pages_read else None,
            publishes_outcomes=out.publishes_outcomes if deps.pages_read else None,
            mission_fit_note=out.mission_fit_note,
            evidence_ids=list(deps.web_evidence_ids),
        )

    def _has_independent_source(self, profile: OrgProfile, deps: AgentDeps) -> bool:
        own_host = (urlparse(deps.website_url or "").hostname or "").removeprefix("www.")
        for ev_id in deps.web_evidence_ids:
            ev = self.session.evidence.get(ev_id)
            host = (urlparse((ev.source_url if ev else "") or "").hostname or "").removeprefix("www.")
            if host and host != own_host and not host.endswith("." + own_host):
                return True
        return False

    # ------------------------------------------------------------------ 3. verification

    def _all_findings(self) -> list[Finding]:
        return [f for r in self.reports.values() for f in r.findings]

    def _verify(self) -> None:
        self.verified = True
        session = self.session
        session.stage("verify", "started")
        findings = self._all_findings()
        try:
            self.verification = verify.verify_findings(findings, session.evidence)
        except Exception as exc:
            log.exception("verify_findings failed")
            self.errors.append(f"Verification failed ({type(exc).__name__}); unverified findings were withheld.")
            self.verification = VerificationReport(
                checks=[
                    ClaimCheck(finding_id=f.id, status="unverified_number", detail="verifier unavailable")
                    for f in findings
                ],
                flagged_count=len(findings),
            )
        self.checks = {c.finding_id: c for c in self.verification.checks}
        by_id = {f.id: f for f in findings}
        for check in self.verification.checks:
            finding = by_id.get(check.finding_id)
            if finding is None or check.status not in FLAGGED:
                continue
            reason = {
                "unverified_number": "a number did not match the evidence"
                + (f" ({', '.join(check.unmatched_numbers)})" if check.unmatched_numbers else ""),
                "missing_evidence": "it has numbers but cites no evidence",
                "unknown_evidence_id": "it cites an evidence id that does not exist",
            }[check.status]
            if self.defenses_on:
                self.removed[finding.id] = reason
            session.security(
                SecurityEvent(
                    kind="unverified_claim",
                    severity="warning",
                    agent=finding.agent,
                    ein=finding.ein,
                    detail=(f"Finding {finding.id} removed from the memo: {reason}."
                            if self.defenses_on else f"Finding {finding.id} kept although {reason} (defenses off)."),
                    snippet=short(finding.text, 240),
                )
            )
        session.stage("verify", "done")

    # ------------------------------------------------------------------ 4. audit

    async def _audit(self) -> None:
        session = self.session
        session.stage("audit", "started")
        findings = self._all_findings()
        if findings and session.remaining_seconds() > MIN_SECONDS_FOR_AUDITOR:
            questions = {
                p.ein: _dedupe(
                    [q for r in self.reports.values() if r.ein == p.ein for q in r.questions_for_charity]
                )
                for p in self.profiles
            }
            deps = AgentDeps(session=session, agent_key="auditor", ein=None, limits=AUDITOR_LIMITS)
            outcome = await run_agent(
                session,
                agent=auditor_agent.agent,
                agent_key="auditor",
                role=auditor_agent.ROLE,
                label=auditor_agent.ROLE,
                ein=None,
                prompt=auditor_agent.build_prompt(
                    self.profiles, findings, self.checks, session.security_events, questions,
                    donor_note=self.req.donor_note or "",
                ),
                deps=deps,
                usage_limits=AUDITOR_LIMITS.usage_limits(),
                timeout=self._agent_timeout(),
                model=self.model,
                summarize=auditor_agent.summarize,
            )
            if outcome.status == "done":
                self.audit_ran = True
                out = outcome.output
                known = {f.id for f in findings}
                for fid in out.remove_finding_ids:
                    fid = fid.strip()
                    if fid in known and fid not in self.removed:
                        self.removed[fid] = "the auditor found it overstated or unsupported"
                self.auditor_notes = _dedupe(list(out.notes), 8)
                eins = {p.ein for p in self.profiles}
                self.added_questions = {
                    ein: _dedupe(list(qs), 3) for ein, qs in out.extra_questions.items() if ein in eins and qs
                }
            else:
                self.auditor_notes = ["The auditor agent did not finish; deterministic verification still applied."]
        elif findings:
            self.auditor_notes = ["The auditor was skipped to stay within the run time limit."]
        session.stage("audit", "done")

    # ------------------------------------------------------------------ 5. scoring

    def _score(self) -> None:
        self.session.stage("scoring", "started")
        for profile in self.profiles:
            metrics = self.metrics.get(profile.ein) or FinancialMetrics(ein=profile.ein)
            try:
                card = scoring.score_charity(profile, metrics, self.impacts.get(profile.ein), self.req.weights)
            except Exception as exc:
                log.exception("scoring failed for %s", profile.ein)
                self.errors.append(f"EIN {profile.ein}: scoring failed ({type(exc).__name__}).")
                card = CharityScorecard(ein=profile.ein, name=profile.name, is_demo=profile.is_demo)
            self.scorecards[profile.ein] = card
        self.session.stage("scoring", "done")

    # ------------------------------------------------------------------ 6. memo

    def _kept_findings(self) -> dict[str, list[Finding]]:
        kept: dict[str, list[Finding]] = {p.ein: [] for p in self.profiles}
        for report in self.reports.values():
            if report.status != "done":
                continue
            for f in report.findings:
                if f.id not in self.removed and f.ein in kept:
                    kept[f.ein].append(f)
        return kept

    def _questions(self, ein: str) -> list[str]:
        qs = [q for r in self.reports.values() if r.ein == ein for q in r.questions_for_charity]
        return _dedupe(qs + self.added_questions.get(ein, []))

    def _could_not_verify(self, ein: str) -> list[str]:
        items = [c for r in self.reports.values() if r.ein == ein for c in r.could_not_verify]
        for r in self.reports.values():
            if r.ein != ein:
                continue
            if r.status != "done":
                items.append(f"The {r.role} agent did not finish, so its part of the review is missing.")
            for f in r.findings:
                if f.id in self.removed:
                    items.append(f"Removed from the memo because {self.removed[f.id]}: {short(f.text, 200)}")
        metrics = self.metrics.get(ein)
        if metrics:
            for m in metrics.metrics.values():
                if m.value is None and m.key != "program_expense_share" and m.reason_missing:
                    items.append(f"{m.label}: {m.reason_missing}")
        return _dedupe(items, 12)

    async def _write_memo(self) -> None:
        session = self.session
        session.stage("memo", "started")
        draft: MemoAgentOutput | None = None
        kept = self._kept_findings()
        if session.remaining_seconds() > MIN_SECONDS_FOR_MEMO:
            deps = AgentDeps(session=session, agent_key="memo", ein=None, limits=MEMO_LIMITS)
            outcome = await run_agent(
                session,
                agent=memo_agent.agent,
                agent_key="memo",
                role=memo_agent.ROLE,
                label=memo_agent.ROLE,
                ein=None,
                prompt=memo_agent.build_prompt(
                    weights=self.req.weights,
                    donor_note=self.req.donor_note or "",
                    profiles=self.profiles,
                    scorecards=self.scorecards,
                    kept_findings=kept,
                    questions={p.ein: self._questions(p.ein) for p in self.profiles},
                    could_not_verify={p.ein: self._could_not_verify(p.ein) for p in self.profiles},
                    auditor_notes=self.auditor_notes,
                ),
                deps=deps,
                usage_limits=MEMO_LIMITS.usage_limits(),
                timeout=self._agent_timeout(),
                model=self.model,
                summarize=memo_agent.summarize,
            )
            if outcome.status == "done":
                draft = outcome.output
        self.memo = self._assemble_memo(draft)
        session.stage("memo", "done")

    def _checked_text(self, text: str, label: str) -> str:
        text = (text or "").strip()
        if not text:
            return text
        try:
            check = verify.verify_text(text, self.session.evidence, label)
        except Exception as exc:
            log.warning("verify_text failed: %s", exc)
            return text
        if self.defenses_on and check.status in FLAGGED:
            try:
                kept_text, dropped = verify.remove_unverified_sentences(text, self.session.evidence)
            except Exception as exc:
                log.warning("remove_unverified_sentences failed: %s", exc)
                kept_text, dropped = "", [text]
            if dropped:
                check.detail = (
                    (check.detail + " ").lstrip()
                    + f"Removed {len(dropped)} sentence(s) with numbers that are not in the evidence ledger."
                )
                self.session.security(
                    SecurityEvent(
                        kind="unverified_claim",
                        severity="warning",
                        agent="memo",
                        detail=f"Removed {len(dropped)} sentence(s) from the memo {label.split('.')[-1]} "
                        "because their numbers did not match the evidence.",
                        snippet=short(" ".join(dropped), 240),
                    )
                )
            text = kept_text
        self.text_checks.append(check)
        return text

    def _fallback_headline(self) -> str:
        cards = [self.scorecards.get(p.ein) for p in self.profiles]
        ranked = sorted(
            [c for c in cards if c is not None and c.overall is not None and c.band != "insufficient_data"],
            key=lambda c: c.overall or 0,
            reverse=True,
        )
        if not ranked:
            return "The free IRS data is not enough to rate these charities; ask them for the missing information before giving."
        top = ranked[0]
        if len(self.profiles) == 1:
            return f"{top.name} is a {BAND_WORDS[top.band]} on your priorities; ask the questions below before giving."
        return f"{top.name} is the strongest fit on your priorities among the charities reviewed; ask the questions below before giving."

    def _method_note(self) -> str:
        parts = [
            "Financial figures come from the newest Form 990 filing with extracted data in ProPublica's free "
            "Nonprofit Explorer API, which can be a year or more behind the newest PDF filing, and from "
            "deterministic calculations; the AI agents interpret these figures but do not produce them.",
        ]
        if self.defenses_on:
            parts.append(
                "Web pages were sanitized before any model read them (hidden text and instructions aimed at AI "
                "removed), and a deterministic verifier removed findings whose numbers did not match the evidence ledger."
            )
        else:
            parts.append(
                "Defenses were turned off for this run (safety demonstration): web content was not sanitized and "
                "unverified findings were kept."
            )
        parts.append(
            "Program-spending share is not in that extract, so it is listed as a question for each charity. "
            "Scores use a documented rubric (docs/scoring-rubric.md); its thresholds are hypotheses, not facts."
        )
        return " ".join(parts)

    def _assemble_memo(self, draft: MemoAgentOutput | None, partial_reason: str | None = None) -> GivingMemo:
        kept = self._kept_findings()
        drafts = {c.ein: c for c in (draft.charities if draft else [])}
        sections: list[CharitySection] = []
        for profile in self.profiles:
            ein = profile.ein
            card = self.scorecards.get(ein)
            own = {f.id: f for f in kept.get(ein, [])}
            d = drafts.get(ein)

            def pick(ids: list[str], stance: str) -> list[Finding]:
                chosen = [own[i.strip()] for i in ids if i.strip() in own]
                if not chosen:
                    chosen = [f for f in own.values() if f.stance == stance]
                return chosen[:4]

            strengths = pick(d.strength_finding_ids if d else [], "strength")
            concerns = pick(d.concern_finding_ids if d else [], "concern")
            questions = _dedupe(list(d.questions_for_charity) if d else [], 5) or self._questions(ein)[:5]
            if not any("program" in q.lower() for q in questions):
                questions.append(PROGRAM_QUESTION)
            band = card.band if card else "insufficient_data"
            one_line = self._checked_text(d.one_line, f"memo.{ein}.one_line") if d else ""
            if not one_line:
                one_line = f"Rated {BAND_WORDS.get(band, band)} on the donor's priorities by the scoring rubric."
            sections.append(
                CharitySection(
                    ein=ein,
                    name=profile.name,
                    is_demo=profile.is_demo,
                    band=band,
                    overall=card.overall if card else None,
                    one_line=one_line,
                    strengths=strengths,
                    concerns=concerns,
                    questions_for_charity=_dedupe(questions, 6),
                    could_not_verify=self._could_not_verify(ein),
                )
            )

        if draft is not None:
            headline = self._checked_text(draft.headline, "memo.headline") or self._fallback_headline()
            summary = self._checked_text(draft.summary, "memo.summary")
            recommendation = self._checked_text(draft.recommendation, "memo.recommendation")
        else:
            headline = self._fallback_headline()
            summary = " ".join(
                f"{s.name}: {BAND_WORDS.get(s.band, s.band)} under the scoring rubric." for s in sections
            )
            recommendation = (
                "Ask each charity the questions listed below and compare their answers before deciding. "
                "The memo writer did not finish, so this summary comes from the scorecards only."
            )
        if partial_reason:
            headline = partial_reason
        return GivingMemo(
            headline=headline,
            summary=summary,
            recommendation=recommendation,
            charities=sections,
            method_note=self._method_note(),
            text_checks=self.text_checks,
        )

    # ------------------------------------------------------------------ stops and finish

    def _fail(self, message: str) -> None:
        self.status = "error"
        self.errors.append(message)

    async def _budget_stop(self) -> None:
        session = self.session
        session.stopped_by_budget = True
        self.status = "stopped_budget"
        spent = 0.0
        try:
            spent = session.budget.total_usd
        except Exception:
            pass
        session.security(
            SecurityEvent(
                kind="budget_stop",
                severity="blocked",
                detail=f"The run reached its ${self.budget_usd:.2f} budget cap (spent ${spent:.4f}); "
                "remaining agents were cancelled.",
            )
        )
        self.errors.append("Stopped at the run budget cap.")
        for key, report in self.reports.items():
            if report.status == "stopped":
                report.summary = "Stopped at the budget cap before finishing."
        self._finish_deterministic(
            partial_reason="This run stopped at its budget cap; the scores and findings below use only the evidence gathered before the stop."
        )
        session.emit_spend()

    def _finish_deterministic(self, partial_reason: str) -> None:
        if not self.profiles:
            return
        try:
            if not self.verified:
                self._verify()
            if not self.scorecards:
                self._score()
            if self.memo is None:
                self.memo = self._assemble_memo(None, partial_reason=partial_reason)
        except Exception:
            log.exception("deterministic finish failed")

    def result(self) -> DiligenceResult:
        try:
            usage = self.session.budget.snapshot(stopped_by_budget=self.session.stopped_by_budget)
        except Exception:
            from app.schemas import RunUsage

            usage = RunUsage(model=self.settings.model_name, budget_usd=self.budget_usd,
                             stopped_by_budget=self.session.stopped_by_budget)
        # Agents run in parallel, so the run total reports wall-clock time, not the sum of agent times.
        usage.total.seconds = round(time.monotonic() - self.started_monotonic, 2)
        audit_report = None
        if self.reports:
            audit_report = AuditReport(
                verification=self.verification,
                auditor_notes=self.auditor_notes,
                removed_finding_ids=list(self.removed),
                added_questions=self.added_questions,
            )
        orgs = [
            OrgSearchResult(
                ein=p.ein,
                name=p.name,
                city=p.city,
                state=p.state,
                ntee_code=p.ntee_code,
                subsection_code=p.subsection_code,
                latest_revenue=p.filings[0].total_revenue if p.filings else None,
                is_demo=p.is_demo,
            )
            for p in self.profiles
        ]
        return DiligenceResult(
            run_id=self.run_id,
            created_at=self.created_at,
            status=self.status,  # type: ignore[arg-type]
            error=" ".join(self.errors) or None,
            defenses_on=self.defenses_on,
            request=self.req,
            orgs=orgs,
            metrics=[self.metrics[p.ein] for p in self.profiles if p.ein in self.metrics],
            reports=list(self.reports.values()),
            audit=audit_report,
            scorecards=[self.scorecards[p.ein] for p in self.profiles if p.ein in self.scorecards],
            memo=self.memo,
            evidence=self.session.evidence,
            security_events=self.session.security_events,
            usage=usage,
        )

    def _finish(self) -> DiligenceResult:
        session = self.session
        result = self.result()
        try:
            if result.usage.total.cost_usd > 0:
                self.daily.add(result.usage.total.cost_usd)
        except Exception as exc:
            log.warning("daily budget update failed: %s", exc)
        if result.status == "error":
            event = session.emit("error", {"message": result.error, "partial": result}, queue=False)
        else:
            event = session.emit("final", result, queue=False)
        try:
            audit.append_run(result, session.events)
        except Exception as exc:
            log.warning("audit.append_run failed: %s", exc)
        if session.queue is not None:
            session.queue.put_nowait(event)
            session.queue.put_nowait(None)
        return result


async def run_diligence(
    req: DiligenceRequest,
    *,
    queue: asyncio.Queue | None = None,
    model: Any = None,
    settings: Settings | None = None,
    run_id: str | None = None,
) -> DiligenceResult:
    """Run the whole pipeline. Puts every event on `queue` (if given) and a final None sentinel."""
    run = DiligenceRun(req, settings=settings or get_settings(), model=model, queue=queue, run_id=run_id)
    try:
        return await run.execute()
    except BaseException:
        if queue is not None:
            queue.put_nowait(None)
        raise
