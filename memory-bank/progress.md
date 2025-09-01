# Progress

## What Works

- Project-level session lock implemented and integrated:
  - Stateless, dashboard-backed lock persisted under the single “Active Session” section between `<!-- marker:MERGEBOT_SESSION_LOCK -->` markers.
  - Default TTL is 10 minutes (600s) with heartbeat refresh (~200s) while a run is active.
  - Both ondemand and webhook-triggered runs acquire the same project-scoped lock, preventing concurrent sessions across instances.
  - Layout normalization ensures only one “Active Session” header; the lock updater only replaces the content between markers.
- Self-hosted Mergebot runs in ondemand mode with GitHub App authentication (raw PEM via env or config), validated end-to-end.
- Documentation updated across Architecture, Usage, Operations, and Capabilities to describe session lock scope, TTL, and behavior.
- PAT flow still present for GitLab and backward compatibility.

## What's Left to Build (Detailed TODO)

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

- Project session lock (10-minute TTL + heartbeat) is implemented and documented.
- Ondemand and webhook flows both respect the session lock to avoid duplicate analysis/comments.
- Documentation updated to reflect concurrency control, behavior on busy lock, and layout normalization.
- Next phase focuses on tests, optional configuration knobs, and webhook hardening (HMAC, dedupe bursts), as well as PEM normalization for GitHub App private key handling.
