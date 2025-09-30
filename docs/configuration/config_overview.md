# Configuration Overview

Mergebot is configured via a YAML file and environment variables.

- **Project-level config**: `.mergebot.yml` in your repository
- **Server config**: `mergebot/config.yaml`
- **Approval policy**: Optional, for auto-approval logic

See the sidebar for approval policy details and the full config schema.

## Auto‑Merge (Optional)

You can enable safe auto‑merge with explicit guardrails. Configure under the top‑level `merge` block:

- `enabled`: Explicit opt‑in to auto‑merge (default: false)
- `threshold`: Optional. If unset, falls back to `approval_policy.threshold`
- `strategy`: `repo_default` | `merge` | `squash` | `rebase`
- `rules`:
  - `ci_passed`: Require CI to be green (failing CI blocks)
  - `ci_strict`: If true, treat unknown/no CI as failure. If false (default), allow projects without CI configured.
  - `no_changes_requested`: Block if any review has “changes requested”
  - `mergeable`: Require no conflicts
  - `approval_state`: Require platform approval state satisfied
  - `branch_prefixes`: Optional allow‑list for source branches (e.g., `feature/`, `bugfix/`)

Example:
```yaml
merge:
  enabled: true
  threshold: null
  strategy: repo_default
  rules:
    ci_passed: true
    ci_strict: false
    no_changes_requested: true
    mergeable: true
    approval_state: true
    branch_prefixes:
      - "feature/"
      - "bugfix/"
```

Notes:
- Threshold requirement: Auto-merge only runs when a merge threshold is available. Set `merge.threshold`, or rely on `approval_policy.threshold`. If neither is defined (or the impact score is unavailable), Mergebot will skip the merge and explain why in a comment.
- Draft/WIP PRs/MRs are never auto‑merged (hard rule).
- CI behavior: With `ci_passed: true`, failing CI blocks. If no pipelines/checks are configured, CI is treated as unknown and allowed by default; set `ci_strict: true` to block when CI is unknown/not configured.
- If `branch_prefixes` is set, only source branches starting with one of the listed prefixes are eligible for auto‑merge.
- Mergebot always posts a concise comment explaining whether it merged or skipped, including the impact score, thresholds, and guardrail reasons.

> **Tip:** For onboarding and setup, see [Onboarding](../usage/onboarding.md).
