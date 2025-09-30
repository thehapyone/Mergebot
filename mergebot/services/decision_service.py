from typing import Any, Dict

from mergebot.services import approval_service, merge_service
from mergebot.utils import get_platform_type
from mergebot.validator.config import get_runtime_config
from mergebot.validator.logging_config import logger


def _is_conclusive_impact_assessment(data: dict) -> bool:
    """
    An assessment is conclusive only if BOTH recommendation and score were extracted.
    - recommendation: non-empty after trimming
    - score: non-empty and not in {"N/A","NA"} (case-insensitive)
    """
    if not isinstance(data, dict):
        return False
    rec = str(data.get("recommendation", "") or "").strip()
    score = str(data.get("score", "") or "").strip()
    if not rec or not score:
        return False
    if score.upper() in {"N/A", "NA"}:
        return False
    return True


def _build_messages() -> Dict[str, str]:
    pr_style = "MR" if get_platform_type() == "gitlab" else "PR"
    return {
        "approval": (
            f"✅ {pr_style} has been auto-approved as recommended in the Impact Assessment Report (see assessment report).\n"
            "This action has been automated as per the established policy.\n"
            "If CI or downstream issues arise, please review the report or raise an issue manually."
        ),
        "not_approved": (
            f"❌ {pr_style} has not been auto-approved as per the Impact Assessment Report.\n"
            "Please review the report and take necessary actions manually."
        ),
        "inconclusive": (
            "⚠️ Impact Assessment result appears inconclusive or not in the expected format.\n\n"
            "Recommended next steps:\n"
            "- Consider using a more capable AI model for the Impact Evaluator crew.\n"
            "- Review your approval configuration (docs/configuration/approval_policy.md).\n"
            "- Review the Mergebot logs for potential errors or truncation.\n\n"
            "This review will be held for human attention. No auto-approval has been performed."
        ),
    }


async def post_merge_failed_reason(pr_id, score_val, merge_threshold, reasons):
    reasons_text = ", ".join(reasons) if reasons else "Unknown reason"
    msg = (
        "⚠️ Merge skipped\n"
        f"- Reason(s): {reasons_text}\n"
        f"- Weighted score: {score_val if score_val else 'Unavailable'} (merge threshold: {merge_threshold if merge_threshold else 'Unavailable'})\n"
    )
    await approval_service.post_comment(pr_id, msg)


def generate_final_decision(
    impact_assessment, approved_flag, action_note, analysis_link
):
    final_decision = {
        "recommendation": impact_assessment.get("recommendation"),
        "impact_score": impact_assessment.get("score"),
        "action_taken": action_note,
        "analysis_link": analysis_link,
        "approved": approved_flag,
    }

    return final_decision


async def process_decision(
    pr_id: int, impact_assessment: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Orchestrates posting the assessment, approving if applicable, and auto-merging under guardrails.

    Returns:
      final_decision: dict with recommendation, impact_score, action_taken, analysis_link, approved
      analysis_link: permalink to the posted analysis/comment
      approved_flag: bool indicating whether approval was performed
    """
    messages = _build_messages()
    rec = str(impact_assessment.get("recommendation", "") or "").strip().lower()
    report = str(impact_assessment.get("report", "") or "")

    approved_flag = False
    action_note = ""
    analysis_link = ""

    # Handle inconclusive assessment
    if not _is_conclusive_impact_assessment(impact_assessment):
        analysis_link = await approval_service.post_comment(
            pr_id, messages["inconclusive"]
        )
        action_note = "Human review required (inconclusive)"
        final_decision = generate_final_decision(
            impact_assessment,
            approved_flag,
            action_note,
            analysis_link,
            recommendation=action_note,
        )
        final_decision["recommendation"] = (
            action_note  # Override recommendation for inconclusive case
        )
        return final_decision

    # Post the impact assessment report first
    analysis_link = await approval_service.post_comment(pr_id, report)

    # If recommended to approve
    if "approve" in rec:
        try:
            await approval_service.approve_change(pr_id)
            await approval_service.post_comment(pr_id, messages["approval"])
            action_note = "Approved"
            approved_flag = True
        except Exception as e:
            logger.error(f"Approval action failed: {e}")
            action_note = f"Approval failed: {e}"

        # Auto-merge stage (if enabled)
        cfg = get_runtime_config(as_pydantic=True)
        merge_cfg = getattr(cfg, "merge", None)
        if approved_flag and merge_cfg and merge_cfg.enabled:
            # Parse numeric impact score
            raw_score = impact_assessment.get("score")
            score_val = merge_service.parse_first_float(raw_score)

            # Threshold fallback: merge.threshold -> approval_policy.threshold
            approval_threshold = (
                cfg.approval_policy.threshold if cfg.approval_policy else None
            )
            merge_threshold = (
                merge_cfg.threshold
                if merge_cfg.threshold is not None
                else approval_threshold
            )
            score_ok_for_merge = (
                (score_val is not None)
                and (merge_threshold is not None)
                and (score_val <= merge_threshold)
            )

            # Early exit if score disqualifies merge
            if not score_ok_for_merge:
                reasons = [
                    (
                        "Impact score above merge threshold"
                        if score_val is not None
                        else "Impact score unavailable"
                    )
                ]
                await post_merge_failed_reason(
                    pr_id, score_val, merge_threshold, reasons
                )
                final_decision = generate_final_decision(
                    impact_assessment, approved_flag, action_note, analysis_link
                )
                return final_decision, analysis_link, approved_flag

            # Pre-merge guardrails
            status = await merge_service.get_status(pr_id)
            rules_dict = (
                merge_cfg.rules.model_dump()
                if hasattr(merge_cfg.rules, "model_dump")
                else dict(merge_cfg.rules)
            )
            allowed_by_rules, reasons = merge_service.evaluate_rules(
                status, rules=rules_dict, enforce_never_merge_draft=True
            )

            # Source branch prefix rule (allow-list).
            prefixes = getattr(
                getattr(merge_cfg, "rules", None), "branch_prefixes", None
            )
            if prefixes:
                source_branch = (status.get("source_branch") or "").strip()
                if not any(
                    isinstance(p, str) and source_branch.startswith(p) for p in prefixes
                ):
                    allowed_by_rules = False
                    reasons.append(
                        f"Source branch '{source_branch or '?'}' not allowed by prefix rules"
                    )

            # Early exit if rules disallow merge
            if not allowed_by_rules:
                await post_merge_failed_reason(
                    pr_id, score_val, merge_threshold, reasons
                )
                final_decision = generate_final_decision(
                    impact_assessment, approved_flag, action_note, analysis_link
                )
                return final_decision, analysis_link, approved_flag

            # Perform merge
            try:
                result = await merge_service.merge_change(
                    pr_id, strategy=merge_cfg.strategy
                )
                summary = (
                    f"✅ Auto-merged using strategy: {merge_cfg.strategy}\n"
                    f"- Weighted score: {score_val} (threshold: {merge_threshold})\n"
                    f"- CI: {status.get('ci_passed')}, "
                    f"Reviews: approved={status.get('reviews', {}).get('approved')}, "
                    f"changes_requested={status.get('reviews', {}).get('changes_requested')}, "
                    f"Mergeable: {status.get('mergeable')}, "
                    f"Approval state: {status.get('approval_state')}\n"
                    f"- Result: {result}"
                )
                await approval_service.post_comment(pr_id, summary)
                action_note = "Approved and merged"
            except Exception as e:
                logger.error(f"Merge action failed: {e}")
                await approval_service.post_comment(pr_id, f"⚠️ Merge failed: {e}")

        elif approved_flag:
            # Inform that merge is disabled
            await approval_service.post_comment(
                pr_id, "Auto-merge is disabled by configuration. PR approved."
            )

    else:
        # Not recommended to approve
        try:
            await approval_service.post_comment(pr_id, messages["not_approved"])
            action_note = "Not approved"
        except Exception as e:
            logger.error(f"Failed to post 'not approved' comment: {e}")
            action_note = f"Failed to post comment: {e}"

    final_decision = generate_final_decision(
        impact_assessment, approved_flag, action_note, analysis_link
    )
    return final_decision
