"""Reviewer verdict schema and output-guardrail contracts (proposal §3.4)."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from mergebot.crews.schemas import (
    Finding,
    ReviewerVerdict,
    make_findings_guardrail,
)


def make_verdict(**finding_overrides):
    finding = {
        "title": "Unbounded query",
        "severity": "high",
        "file": "known.py",
        "line": 12,
        "evidence": "cursor.execute(query)",
        "recommendation": "Add a limit",
        **finding_overrides,
    }
    return ReviewerVerdict(
        score=5.0, confidence="medium", summary="summary", findings=[Finding(**finding)]
    )


def output_with(verdict=None, raw=""):
    return SimpleNamespace(pydantic=verdict, raw=raw)


class TestVerdictSchema:
    def test_score_bounds_enforced(self):
        with pytest.raises(ValidationError):
            ReviewerVerdict(score=10.5, confidence="high", summary="s")
        with pytest.raises(ValidationError):
            ReviewerVerdict(score=-0.1, confidence="high", summary="s")

    def test_severity_and_confidence_literals_enforced(self):
        with pytest.raises(ValidationError):
            Finding(title="t", severity="urgent", evidence="e", recommendation="r")
        with pytest.raises(ValidationError):
            ReviewerVerdict(score=1.0, confidence="certain", summary="s")


class TestFindingsGuardrail:
    def test_valid_verdict_passes_and_returns_normalized_json(self):
        guardrail = make_findings_guardrail(lambda path: path == "known.py")
        verdict = make_verdict()
        ok, payload = guardrail(output_with(verdict))
        assert ok
        assert ReviewerVerdict.model_validate_json(payload) == verdict

    def test_unknown_file_is_rejected(self):
        guardrail = make_findings_guardrail(lambda path: False)
        ok, error = guardrail(output_with(make_verdict(file="ghost.py")))
        assert not ok
        assert "ghost.py" in error

    def test_missing_evidence_rejected_for_medium_and_above(self):
        guardrail = make_findings_guardrail(lambda path: True)
        for severity in ("medium", "high", "critical"):
            ok, error = guardrail(output_with(make_verdict(severity=severity, evidence="   ")))
            assert not ok, severity
            assert "evidence" in error

    def test_missing_evidence_allowed_below_medium(self):
        guardrail = make_findings_guardrail(lambda path: True)
        for severity in ("info", "low"):
            ok, _ = guardrail(output_with(make_verdict(severity=severity, evidence="")))
            assert ok, severity

    def test_file_none_is_allowed_for_repo_wide_findings(self):
        guardrail = make_findings_guardrail(lambda path: False)
        ok, _ = guardrail(output_with(make_verdict(file=None)))
        assert ok

    def test_none_checker_skips_file_validation_but_keeps_evidence_rule(self):
        guardrail = make_findings_guardrail(None)
        ok, _ = guardrail(output_with(make_verdict(file="anything.py")))
        assert ok
        ok, error = guardrail(output_with(make_verdict(evidence="")))
        assert not ok
        assert "evidence" in error

    def test_raw_json_path_when_pydantic_not_populated(self):
        """Guardrails can run before CrewAI converts raw output to the model."""
        guardrail = make_findings_guardrail(lambda path: True)
        verdict = make_verdict()
        ok, payload = guardrail(output_with(raw=verdict.model_dump_json()))
        assert ok
        assert ReviewerVerdict.model_validate_json(payload) == verdict

    def test_fenced_raw_json_is_unwrapped(self):
        guardrail = make_findings_guardrail(lambda path: True)
        raw = f"```json\n{make_verdict().model_dump_json()}\n```"
        ok, _ = guardrail(output_with(raw=raw))
        assert ok

    def test_invalid_raw_output_reports_schema_error(self):
        guardrail = make_findings_guardrail(lambda path: True)
        ok, error = guardrail(output_with(raw="not json at all"))
        assert not ok
        assert "ReviewerVerdict schema" in error
