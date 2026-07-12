"""Decision-service contract: exact enum matching and render-surface mapping.

The historical bug fixed in Phase A: the recommendation branch used a substring
check (`"approve" in rec`), so phrasings like "Do not approve" were treated as
approvals. Decisions now match the scoring enum exactly.
"""

from types import SimpleNamespace

import pytest

from mergebot.services import decision_service


@pytest.fixture
def actions(monkeypatch):
    """Record side effects; keep every external call offline."""
    recorded = SimpleNamespace(comments=[], approved=[])

    async def post_comment(pr_id, body, runtime):
        recorded.comments.append(body)
        return "https://example.com/comment/1"

    async def approve_change(pr_id, runtime):
        recorded.approved.append(pr_id)
        return "approved"

    monkeypatch.setattr(decision_service.approval_service, "post_comment", post_comment)
    monkeypatch.setattr(decision_service.approval_service, "approve_change", approve_change)
    monkeypatch.setattr(decision_service, "_get_bot_identity", lambda runtime: "mergebot-bot")
    return recorded


def make_runtime():
    # config=None keeps merge disabled (getattr(None, "merge", None) is None).
    return SimpleNamespace(platform_type="github", config=None, project_path="acme/repo")


def make_assessment(recommendation, score="5.0"):
    return {
        "score": score,
        "recommendation": recommendation,
        "report": "# Impact Assessment Report for PR/MR #7\n\nbody",
    }


class TestRecommendationMatching:
    async def test_do_not_approve_is_not_treated_as_approval(self, actions):
        """Regression: substring matching turned 'Do not approve' into an approval."""
        decision = await decision_service.process_decision(
            7, make_assessment("Do not approve"), make_runtime()
        )
        assert actions.approved == []
        assert decision["approved"] is False
        assert decision["action_taken"] == "Not approved"

    async def test_display_phrase_does_not_trigger_approval(self, actions):
        """Only the enum value approves — not the human-readable render of it."""
        decision = await decision_service.process_decision(
            7, make_assessment("Auto-approve and merge"), make_runtime()
        )
        assert actions.approved == []
        assert decision["approved"] is False

    async def test_auto_approve_enum_approves(self, actions):
        decision = await decision_service.process_decision(
            7, make_assessment("auto-approve"), make_runtime()
        )
        assert actions.approved == [7]
        assert decision["approved"] is True
        assert decision["action_taken"] == "Approved"

    async def test_human_review_enum_rejects(self, actions):
        decision = await decision_service.process_decision(
            7, make_assessment("human-review"), make_runtime()
        )
        assert actions.approved == []
        assert decision["approved"] is False


class TestRenderSurfaces:
    async def test_final_decision_carries_display_phrase(self, actions):
        """The dashboard row gets the rendered phrasing, not the raw enum."""
        approved = await decision_service.process_decision(
            7, make_assessment("auto-approve", score="1.5"), make_runtime()
        )
        assert approved["recommendation"] == "Auto-approve and merge"
        assert approved["impact_score"] == "1.5"

        rejected = await decision_service.process_decision(
            7, make_assessment("human-review"), make_runtime()
        )
        assert rejected["recommendation"] == "Requires human review"

    async def test_inconclusive_score_holds_for_human_attention(self, actions):
        decision = await decision_service.process_decision(
            7, make_assessment("auto-approve", score="N/A"), make_runtime()
        )
        assert actions.approved == []
        assert decision["approved"] is False
        assert decision["recommendation"] == "Human review required (inconclusive)"
        assert any("inconclusive" in c.lower() for c in actions.comments)
