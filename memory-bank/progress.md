# Progress

## What Works

- Detailed pipeline (CI) summaries for both GitHub (Actions workflow runs) and GitLab pipelines, unified in formatting and available in both PR output and as tool calls.
  - GitHub: For each PR, finds the best matching workflow run, fetches metadata, jobs, errors.
  - Cross-platform: All public and tool interfaces now present pipeline output identically.
  - Docs, Memory Bank, config, and CLI reference all updated for users and integrators.
- Project-level session lock implemented and integrated:
  - Stateless, dashboard-backed lock persisted under the single “Active Session” section between `<!-- marker:MERGEBOT_SESSION_LOCK -->` markers.
  - Default TTL is 10 minutes (600s) with heartbeat refresh (~200s) while a run is active.
  - Both ondemand and webhook-triggered runs acquire the same project-scoped lock, preventing concurrent sessions across instances.
  - Layout normalization ensures only one “Active Session” header; the lock updater only replaces the content between markers.
- Self-hosted Mergebot runs in ondemand mode with GitHub App authentication (raw PEM via env or config), validated end-to-end.
- Documentation updated across Architecture, Usage, Operations, and Capabilities to describe session lock scope, TTL, and behavior.
- PAT flow still present for GitLab and backward compatibility.

## What's Left to Build (Detailed TODO)

### F) Auto-Merge Robustness, CI, and Onboarding

- [x] Support auto-merge with fallback threshold, full guardrails, and cross-platform (GitHub + GitLab) support.
- [x] Add rules.ci_strict option to distinguish “no CI” (allowed by default) from “failing CI” (blocked by default).
- [x] Backwards compatibility: allowed_source_branch_prefixes → rules.branch_prefixes.
- [x] Update onboarding PRs/MRs and default .mergebot.yml to show all new merge options with documented behavior/examples.
- [x] Documentation: config_schema.md and config_overview.md show all merge options, default policies, and notes on CI, branch_prefixes.
- [x] Pipeline integration: get_pipeline_details for both providers; PR summaries and GetPipelineDetails tool now expose all job/run info, errors, and output in a single format.
- [x] Decision logic: Always post reasoned merge summary (merged/skipped + reason), enforce branch allow-list, new CI rules.
- [ ] Monitor for further config/UX improvements as new edge cases appear (including pipeline/log analysis or UX feedback).


### A) Session Lock Hardening
- [ ] Add unit/integration tests for `SessionLockCoordinator`:
  - Acquire vs. busy scenarios, verify-after-write (nonce) behavior, expired lock takeover.
  - Heartbeat extension and ownership change detection.
  - Normalization behavior if markers are missing or layout drift occurs.
- [ ] Optional config knobs (if requested by users):
  - Expose `lock.ttl_seconds` and `lock.refresh_interval_seconds` via config schema + validation.
- [ ] Robust retries and backoff:
  - Add jittered backoff around dashboard reads/writes to handle API rate limits or transient failures.
- [ ] Observability:
  - Emit concise logs/metrics for lock lifecycle (acquire, extend, release, busy/skip).

### B) Webhook-Driven GitHub App Support (Self-Hosted & SaaS)
- [ ] Harden webhook server for GitHub (HMAC signature validation) and extend event handling.
- [ ] Trigger re-review on PR opened/updated/synchronized/reopened; dedupe bursts.
- [ ] Add command-based re-review (e.g., “@mergebot review”, configurable).
- [ ] Ensure ondemand vs webhook runs share core flow without duplication (already align with lock).

### C) Cloud/SaaS mode (separate track)
- [ ] Multi-tenant persistence and OAuth/install flows (DB schema, installation linkage, webhook secrets).
- [ ] Admin tasks and scheduling.

### D) PEM normalization utility
- [ ] Normalize single-line `\\n` secrets to real newlines for `GITHUB_APP_PRIVATE_KEY` before JWT signing.
- [ ] Update onboarding docs to remove the caveat once implemented.

### E) Docs & Examples
- [ ] Add a small “Troubleshooting” note for lock-related issues (e.g., dashboard markers missing, rate limits).


## Current Status

- GitHub Actions pipeline (workflow run) details are fully supported, documented, and integrated in all flows. This brings Mergebot’s PR diagnostics to parity across all major platforms.
- Project session lock (10-minute TTL + heartbeat) is implemented and documented.
- Ondemand and webhook flows both respect the session lock to avoid duplicate analysis/comments.
- Documentation updated to reflect concurrency control, behavior on busy lock, and layout normalization.
- Next phase focuses on:
  - Tests and config for lock/session,
  - Webhook hardening (HMAC, dedupe bursts),
  - PEM normalization for GitHub App private key handling,
  - **Potential future pipeline refinement:** parsing GitHub Actions logs for job warnings (current version: errors only), richer dashboard analytics, UI adjustments based on new data.
