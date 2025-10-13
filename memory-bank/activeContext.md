# Active Context

## Recent Changes (2025-10-13): Dashboard Token Usage Analytics

- **New feature:** The Mergebot dashboard now displays "Total Tokens Used" in the Analytics section, tracking aggregate LLM usage across all PR/MR analyses in a run. A per-crew breakdown is also provided.
- **Rationale:** This metric enables teams to track, optimize, and audit language model resource usage in the project over time—driving transparency and helping control operational costs.
- **Implementation:** Aggregation of usage metrics was added to `ondemand_runner.py` (batch-run), and surfaced in analytics via `dashboard_manager.py`. Plumbing for metrics exposure is in `flow.py`.
- **Documentation:** User, architecture, and template docs, as well as this memory bank, were updated to describe the new analytics fields and design.
- **Design:** The metric reflects *current run* usage only (not cumulative across runs), but is extensibly designed for future historical tracking if desired.

## Core Project State (as of 2025-09-30)

### Recent Changes: Auto-Merge, CI Robustness, GitHub Actions Pipeline Support, Config Evolution

#### GitHub Pipeline Analysis Integration
- Mergebot supports detailed, unified pipeline summaries for GitHub and GitLab in every PR/MR analysis.
- Full refactor of `get_pipeline_details` for GitHub:
  - Decomposed logic into helpers for job fetching, job summarization, log parsing, and timestamp handling, for clarity and DRYness.
  - Log snippet for each failed job now *precisely* extracts lines matching the failed step's `started_at`/`completed_at` time window, with +/-2s tolerance, robust to various timestamp formats.
- Output includes job/step names, relevant error lines, web links, and failed step metadata.
- Implementation is fully modular, testable, and maintainable (Python best practices).
- Documentation updated for code, feature, and best-practice changes.

#### Auto-Merge Features
- Auto-merge for GitHub and GitLab supported and fully configurable.
- merge.enabled: Explicit opt-in required to enable auto-merge.
- Smart merge threshold fallback: merge.threshold (if unset/null) uses approval_policy.threshold.
- Guardrails in merge.rules:
  - ci_passed: Failing CI blocks merges.
  - ci_strict: If false (default), allows merging if no CI exists; if true, blocks when CI state is unknown (i.e., missing).
  - no_changes_requested, mergeable, approval_state: True by default.
  - branch_prefixes: Allow-list for source branch prefixes to restrict which branches are eligible. (E.g., only allow "feature/" or "bugfix/")
- Draft/WIP PRs/MRs always hard-blocked regardless of config.
- Backwards compatibility: allowed_source_branch_prefixes migrated to rules.branch_prefixes if present.

#### Onboarding & Example Config
- Default .mergebot.yml on new repo onboarding includes comprehensive merge block with all new options and clear docs/links.
- Onboarding PR/MR description includes illustrative quick-start example and notes:
  - How to enable, threshold fallback, behavior of ci_passed/ci_strict.
  - Default is robust: unknown/no CI is allowed, failing CI is not.
  - Notes clarify behavior and conservative defaults.

#### Docs
- config_schema, config_overview, onboarding and architecture docs all updated.
- schema and example blocks now show ci_passed, ci_strict, branch_prefixes, and improved explanations about how they interact.

### Implementation and Flow
- Service Layer:
  - merge_service.py: evaluate_rules now considers ci_passed and ci_strict in combination to allow non-CI projects but block failing CI (default: robust, safe for non-CI by default).
  - decision_service.py: surface explicit reasons in merge comments; branch allow-list always enforced.
- Orchestration Flow:
  - All API calls and merge/approval orchestration centralized in service layer.
  - Flow delegates all final actions to decision_service.
  - Flow and config management ensure default merges are transparent, controlled, and cross-platform.

### Important Patterns and Decisions
- Guardrails are now configuration-driven, extensible, and safe for both strict-CI and non-CI workflows.
- Users can get safe auto-merge with simple enable, or make policy stricter (ci_strict: true, branch_prefixes, etc).
- Onboarding is always up-to-date with latest robustness and safety recommendations.

### Next Steps for Project
- [ ] Monitor usage/feedback for clarity or UI improvements on new CI and pipeline details behavior (GitHub and GitLab).
- [ ] Consider logs parsing for GitHub job warnings, and richer pipeline analytics.
- [ ] Consider adding branch regex rules or more granular strategy controls in future.
- [ ] Additional unit and integration test coverage for new onboarding paths and pipeline/path analysis.
