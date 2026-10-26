"""Memo Writer agent: drafts the giving memo from verified findings (owner: agents builder)."""

from __future__ import annotations

from pydantic_ai import Agent

from app.agents.base import AGENT_RETRIES, MODEL_SETTINGS, AgentDeps, load_prompt
from app.schemas import DIMENSION_LABELS, CharityScorecard, Finding, MemoAgentOutput, OrgProfile, Weights

ROLE = "Memo Writer"

BAND_WORDS = {
    "strong_fit": "strong fit",
    "fit_with_questions": "fit with questions",
    "weak_fit": "weak fit",
    "insufficient_data": "insufficient data",
}

agent: Agent[AgentDeps, MemoAgentOutput] = Agent(
    None,
    output_type=MemoAgentOutput,
    deps_type=AgentDeps,
    instructions=load_prompt("memo"),
    name="memo",
    retries=AGENT_RETRIES,
    model_settings=MODEL_SETTINGS,
    defer_model_check=True,
)


def build_prompt(
    *,
    weights: Weights,
    donor_note: str,
    profiles: list[OrgProfile],
    scorecards: dict[str, CharityScorecard],
    kept_findings: dict[str, list[Finding]],
    questions: dict[str, list[str]],
    could_not_verify: dict[str, list[str]],
    auditor_notes: list[str],
) -> str:
    lines = ["Donor priority weights (0 to 5):"]
    for dim, label in DIMENSION_LABELS.items():
        lines.append(f"- {label}: {getattr(weights, dim):g}")
    lines.append("")
    lines.append(f'Donor\'s note: "{donor_note.strip()}"' if donor_note.strip() else "Donor's note: none was given.")
    for profile in profiles:
        card = scorecards.get(profile.ein)
        lines.append("")
        demo = " (fictional DEMO charity)" if profile.is_demo else ""
        lines.append(f"## {profile.name}, EIN {profile.ein}{demo}")
        if card is not None:
            lines.append(f"Band from the rubric: {BAND_WORDS.get(card.band, card.band)}")
            for d in card.dimensions:
                score = "no score (missing inputs)" if d.score is None else f"{d.score:.0f} of 100"
                lines.append(f"- {d.label}: {score}. {d.explanation}")
        own = kept_findings.get(profile.ein) or []
        lines.append("Verified findings you may select:")
        if not own:
            lines.append("- none")
        for f in own:
            lines.append(f"- {f.id} [{f.stance}, {f.dimension}] {f.text}")
        qs = questions.get(profile.ein) or []
        if qs:
            lines.append("Questions proposed by the specialists and auditor:")
            lines.extend(f"- {q}" for q in qs)
        cnv = could_not_verify.get(profile.ein) or []
        if cnv:
            lines.append("Could not verify:")
            lines.extend(f"- {c}" for c in cnv[:8])
    if auditor_notes:
        lines.append("")
        lines.append("Auditor notes:")
        lines.extend(f"- {n}" for n in auditor_notes)
    lines.append("")
    lines.append("Write the MemoAgentOutput. Include one entry in charities for each charity above, in order.")
    return "\n".join(lines)


def summarize(output: MemoAgentOutput) -> str:
    return output.headline
