# Progress

## What Works

- Self-hosted Mergebot runs in ondemand mode with GitHub App authentication (raw PEM via env or config), validated end-to-end.
- All documentation, config, validation, and code align with “raw PEM only.”
- Docs updated to reflect GitHub + GitLab support and PEM guidance (Quickstart GitHub App, Docker Compose, Config Schema, FAQ, Capabilities, README).
- PAT flow still present for backward compatibility.

## What's Left to Build (Detailed TODO for next milestone)

### 1. Webhook-Driven GitHub App Support (Self-Hosted & SaaS)
- [ ] Add robust /webhook endpoint for GitHub App PR/issue_comment events.
- [ ] Parse PR events, trigger re-run when PR is opened, updated, synchronized, reopened.
- [ ] Parse issue/pull_request comment events — trigger re-review if comment content matches e.g. `@mergebot review`.
- [ ] Validate webhook HMAC signature using the app’s webhook secret.
- [ ] Ensure idempotency & queuing (avoid double-processing large bursts).
- [ ] Refactor runner so ondemand vs webhook jobs share core flow (no duplication).

### 2. Cloud/SaaS mode with Public GitHub App (mergebot.dev)
- [ ] Create a hosted GitHub App (mergebot.dev) with correct OAuth callback + webhook URLs.
- [ ] Add OAuth endpoints:
    - `/auth/github/callback` to capture & store user tokens (if needed).
- [ ] Create a minimal multi-tenant Postgres schema:
    - `users` (id, github login/id, authz, ...)
    - `installations` (installation_id, org, repo(s), plan, webhook secret)
- [ ] Adapt config to `MERGEBOT_MODE=cloud` (multi-tenant loads app creds and keys from DB/env, not yaml).
- [ ] Add repo opt-in/out UI (optional for MVP).
- [ ] Support per-repo run scheduling and webhook-push flow (no polling).
- [ ] Add admin task/CLI for triggering jobs or test runs across tenants.
- [ ] Billing/analytics webhooks (future/out of scope).

### 3. Intelligent Rereview via Comment Command
- [ ] Support custom trigger phrase for re-review: on new `issue_comment` on PR, if body contains “@mergebot review” or “/mergebot review” (configurable pattern).
- [ ] Add workflow note to docs & PR comment templates.
- [ ] Must avoid accidental infinite loop (bot must not trigger itself).

### 4. Documentation/Examples
- [ ] Update onboarding & usage docs for webhook & cloud/SaaS usage.
- [ ] Provide example installation YAML for SaaS onboarding, including tips for app approval, callback URL, and webhook secret.

### 5. Upgrade/Legacy Handling
- [ ] Auto-migrate any old configs still using `private_key_path` or path logic; warn user in logs, guide to PEM.
- [ ] CLI command to validate current setup and print SaaS-vs-self-host recommendation.

### 6. PEM normalization utility
- [ ] Add normalization for single-line secrets where `\\n` should be converted to real newlines before JWT signing; update docs to remove caveat once implemented.

---

## Current Status

All ondemand, PEM, and validation foundations are complete. Next phase is to design, implement, and document automated webhook-triggered jobs, SaaS onboarding/user management, and advanced “@mergebot review” triggers.
