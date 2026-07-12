"""Deterministic weighted scoring for reviewer verdicts.

The overall impact score and the auto-approval recommendation are computed here,
in code, from the typed reviewer verdicts and the configured approval policy.
The ImpactEvaluator LLM only writes the narrative and cannot alter either value.
"""

from typing import Final, Literal

from pydantic import BaseModel

from mergebot.crews.schemas import ReviewerVerdict
from mergebot.validator.config import ApprovalPolicy

Recommendation = Literal["auto-approve", "human-review"]

AUTO_APPROVE: Final = "auto-approve"
HUMAN_REVIEW: Final = "human-review"

REVIEWER_WEIGHT_KEYS: Final = (
    "CodeAnalysis",
    "ComplexityAnalysis",
    "TestAnalysis",
    "RiskAnalysis",
)

_RECOMMENDATION_DISPLAY: Final = {
    AUTO_APPROVE: "Auto-approve and merge",
    HUMAN_REVIEW: "Requires human review",
}


class ScoreResult(BaseModel):
    """Outcome of deterministic scoring for one review."""

    overall_score: float
    per_reviewer: dict[str, float]
    threshold: float | None
    recommendation: Recommendation
    weights_used: dict[str, float]


def compute_weighted_score(
    verdicts: dict[str, ReviewerVerdict], policy: ApprovalPolicy | None
) -> ScoreResult:
    """Compute the weighted overall score and recommendation.

    Same semantics as the previous LLM-applied policy: weights are keyed by crew
    name, `overall_score = round(sum(weight * score), 2)`, and the change is
    auto-approved when the score is at or below the threshold.

    `policy=None` is a legal working configuration: equal weights across the four
    reviewers, no threshold, and never auto-approve. The `ApprovalPolicy`
    validator only allows all four weights or no policy at all, so partial
    weights cannot reach this function.

    Raises:
        ValueError: If a reviewer verdict is missing or None.
    """
    missing = [key for key in REVIEWER_WEIGHT_KEYS if verdicts.get(key) is None]
    if missing:
        raise ValueError(f"Missing reviewer verdict(s) for scoring: {', '.join(missing)}")

    if policy is not None:
        weights = {key: policy.weights[key] for key in REVIEWER_WEIGHT_KEYS}
        threshold = policy.threshold
    else:
        weights = dict.fromkeys(REVIEWER_WEIGHT_KEYS, 1 / len(REVIEWER_WEIGHT_KEYS))
        threshold = None

    per_reviewer = {key: verdicts[key].score for key in REVIEWER_WEIGHT_KEYS}
    overall_score = round(sum(weights[key] * per_reviewer[key] for key in REVIEWER_WEIGHT_KEYS), 2)
    recommendation = (
        AUTO_APPROVE if threshold is not None and overall_score <= threshold else HUMAN_REVIEW
    )
    return ScoreResult(
        overall_score=overall_score,
        per_reviewer=per_reviewer,
        threshold=threshold,
        recommendation=recommendation,
        weights_used=weights,
    )


def render_recommendation(recommendation: str) -> str:
    """Human-readable phrasing for render surfaces (comment header, dashboard row).

    Display-only: decisions match the enum value exactly and never parse this text.
    """
    return _RECOMMENDATION_DISPLAY.get(recommendation, recommendation)
