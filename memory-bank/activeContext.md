# Active Context

## Core Project State (as of 2025-09-30)

### Recent Changes: Auto-Merge, CI Robustness, GitHub Actions Pipeline Support, Config Evolution

#### GitHub Pipeline Analysis Integration
- Mergebot now supports reading and displaying detailed pipeline (GitHub Actions workflow run) summaries for GitHub repositories, in addition to existing GitLab pipeline support.
- For every analyzed pull request, Mergebot locates the most relevant Actions run matching the PR's head commit or branch.
- Summaries show run status, conclusion, jobs (status, error/warning counts, web links), in a human-readable format harmonized with GitLab.
- Unified code: Both GitHub and GitLab adapters now implement `get_pipeline_details` and surface this in PR output and via direct tool calls.
- Documentation fully updated: user-facing docs now cover permissions, expected output, and troubleshooting.

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
