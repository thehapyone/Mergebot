"""Golden cases for deterministic weighted scoring (proposal §3.5)."""

import pytest

from mergebot.crews.schemas import ReviewerVerdict
from mergebot.services.scoring import (
    AUTO_APPROVE,
    HUMAN_REVIEW,
    REVIEWER_WEIGHT_KEYS,
    compute_weighted_score,
    render_recommendation,
)
from mergebot.validator.config import ApprovalPolicy


def make_verdicts(code=2.0, complexity=4.0, tests=6.0, risk=8.0):
    scores = dict(zip(REVIEWER_WEIGHT_KEYS, (code, complexity, tests, risk), strict=True))
    return {
        name: ReviewerVerdict(score=score, confidence="high", summary=f"{name} summary")
        for name, score in scores.items()
    }


def make_policy(threshold=3.0, code=0.4, complexity=0.2, tests=0.2, risk=0.2):
    return ApprovalPolicy(
        threshold=threshold,
        weights={
            "CodeAnalysis": code,
            "ComplexityAnalysis": complexity,
            "TestAnalysis": tests,
            "RiskAnalysis": risk,
        },
    )


class TestComputeWeightedScore:
    def test_weighted_sum_with_configured_policy(self):
        result = compute_weighted_score(make_verdicts(), make_policy())

        # 0.4*2 + 0.2*4 + 0.2*6 + 0.2*8 = 4.4, above the 3.0 threshold
        assert result.overall_score == 4.4
        assert result.recommendation == HUMAN_REVIEW
        assert result.threshold == 3.0
        assert result.per_reviewer == {
            "CodeAnalysis": 2.0,
            "ComplexityAnalysis": 4.0,
            "TestAnalysis": 6.0,
            "RiskAnalysis": 8.0,
        }
        assert result.weights_used == {
            "CodeAnalysis": 0.4,
            "ComplexityAnalysis": 0.2,
            "TestAnalysis": 0.2,
            "RiskAnalysis": 0.2,
        }

    def test_score_below_threshold_auto_approves(self):
        result = compute_weighted_score(
            make_verdicts(code=1.0, complexity=1.0, tests=1.0, risk=1.0),
            make_policy(threshold=3.0, code=0.25, complexity=0.25, tests=0.25, risk=0.25),
        )
        assert result.overall_score == 1.0
        assert result.recommendation == AUTO_APPROVE

    def test_score_equal_to_threshold_auto_approves(self):
        result = compute_weighted_score(
            make_verdicts(code=3.0, complexity=3.0, tests=3.0, risk=3.0),
            make_policy(threshold=3.0, code=0.25, complexity=0.25, tests=0.25, risk=0.25),
        )
        assert result.overall_score == 3.0
        assert result.recommendation == AUTO_APPROVE

    def test_overall_score_rounds_to_two_decimals(self):
        result = compute_weighted_score(
            make_verdicts(code=1.11, complexity=2.22, tests=3.33, risk=4.45),
            make_policy(threshold=3.0, code=0.25, complexity=0.25, tests=0.25, risk=0.25),
        )
        # 0.25 * (1.11 + 2.22 + 3.33 + 4.45) = 2.7775
        assert result.overall_score == 2.78

    def test_no_policy_uses_equal_weights_and_never_auto_approves(self):
        # Even an all-zero score must not auto-approve without a policy.
        result = compute_weighted_score(
            make_verdicts(code=0.0, complexity=0.0, tests=0.0, risk=0.0), policy=None
        )
        assert result.overall_score == 0.0
        assert result.threshold is None
        assert result.recommendation == HUMAN_REVIEW
        assert result.weights_used == dict.fromkeys(REVIEWER_WEIGHT_KEYS, 0.25)

    def test_no_policy_equal_weight_average(self):
        result = compute_weighted_score(make_verdicts(), policy=None)
        # mean of 2, 4, 6, 8
        assert result.overall_score == 5.0
        assert result.recommendation == HUMAN_REVIEW

    def test_missing_verdict_raises(self):
        verdicts = make_verdicts()
        del verdicts["RiskAnalysis"]
        with pytest.raises(ValueError, match="RiskAnalysis"):
            compute_weighted_score(verdicts, policy=None)

    def test_none_verdict_raises(self):
        verdicts = make_verdicts()
        verdicts["TestAnalysis"] = None
        with pytest.raises(ValueError, match="TestAnalysis"):
            compute_weighted_score(verdicts, policy=None)


class TestRenderRecommendation:
    def test_enum_values_render_display_phrases(self):
        assert render_recommendation(AUTO_APPROVE) == "Auto-approve and merge"
        assert render_recommendation(HUMAN_REVIEW) == "Requires human review"

    def test_unknown_values_pass_through(self):
        assert render_recommendation("Human review required (inconclusive)") == (
            "Human review required (inconclusive)"
        )
        assert render_recommendation("") == ""
