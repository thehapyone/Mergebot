"""Typed output contracts for the analysis crews, plus their output guardrails.

Every reviewer crew returns a `ReviewerVerdict` (via `output_pydantic`); the
ImpactEvaluator returns an `ImpactReport`. The overall score and recommendation
are computed deterministically in `mergebot.services.scoring`, never by the LLM.
"""

import re
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

Severity = Literal["info", "low", "medium", "high", "critical"]

_EVIDENCE_REQUIRED_SEVERITIES = {"medium", "high", "critical"}

_FENCED_BLOCK_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n(.*)\n\s*```\s*$", re.DOTALL)


class Finding(BaseModel):
    """A single reviewer finding, backed by observed evidence."""

    title: str
    severity: Severity
    file: str | None = Field(
        default=None,
        description="Path as it appears in the diff or repository; None for repo-wide findings",
    )
    line: int | None = None
    evidence: str = Field(description="Quoted code or observed fact — not speculation")
    recommendation: str


class ReviewerVerdict(BaseModel):
    """Structured verdict returned by each of the four reviewer crews."""

    score: float = Field(ge=0.0, le=10.0)
    confidence: Literal["low", "medium", "high"]
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    explored: list[str] = Field(
        default_factory=list,
        description="Audit trail: what the reviewer looked at and why",
    )


class ImpactReport(BaseModel):
    """Narrative produced by the ImpactEvaluator.

    The overall score and recommendation are already decided by deterministic
    scoring when this report is written; the report only carries the prose.
    """

    narrative_markdown: str = Field(
        description="Report body in Markdown, rendered below the code-generated header"
    )
    triage_level: Literal["low", "medium", "high"]


def _verdict_from_task_output(task_output: Any) -> ReviewerVerdict | str:
    """Extract the verdict from a crew TaskOutput; return an error string when invalid.

    The structured-output path populates `task_output.pydantic`; when guardrails
    run before that conversion (raw-string path), the raw JSON is validated here.
    """
    candidate = getattr(task_output, "pydantic", None)
    if isinstance(candidate, ReviewerVerdict):
        return candidate
    raw = str(getattr(task_output, "raw", "") or "")
    fenced = _FENCED_BLOCK_RE.match(raw)
    if fenced:
        raw = fenced.group(1)
    try:
        return ReviewerVerdict.model_validate_json(raw)
    except ValidationError as exc:
        issues = "; ".join(
            f"{'.'.join(str(loc) for loc in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        return f"Output does not match the ReviewerVerdict schema: {issues}"


def make_findings_guardrail(
    is_known_file: Callable[[str], bool] | None,
) -> Callable[[Any], tuple[bool, Any]]:
    """Build the reviewer-output guardrail.

    Rejects findings that cite files absent from the workspace or the diff
    (hallucinated paths) and findings of severity medium or above without
    evidence. `is_known_file` is called at validation time, so the check binds
    to the review that is actually running even though crews are constructed
    before the workspace exists; None disables the file-existence check while
    keeping the evidence requirement.

    Returns a callable with CrewAI's guardrail contract: `(True, raw_json)` on
    success, `(False, actionable_reason)` to trigger a retry.
    """

    def findings_guardrail(task_output: Any) -> tuple[bool, Any]:
        verdict = _verdict_from_task_output(task_output)
        if isinstance(verdict, str):
            return False, verdict

        problems = []
        for finding in verdict.findings:
            if finding.severity in _EVIDENCE_REQUIRED_SEVERITIES and not finding.evidence.strip():
                problems.append(
                    f"Finding '{finding.title}' has severity '{finding.severity}' but no "
                    "evidence; quote the code or observed fact it is based on, or lower "
                    "the severity."
                )
            if finding.file and is_known_file is not None and not is_known_file(finding.file):
                problems.append(
                    f"Finding '{finding.title}' cites file '{finding.file}', which exists "
                    "neither in the repository nor in the diff; use the exact path from "
                    "the PR details or repository context, or omit the file for "
                    "repo-wide findings."
                )
        if problems:
            return False, "\n".join(problems)
        return True, verdict.model_dump_json()

    return findings_guardrail
