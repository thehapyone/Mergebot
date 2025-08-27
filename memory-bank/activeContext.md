# Active Context

## Current Work Focus

- Documentation hygiene and platform coverage:
  - Updated docs to clearly state support for both GitHub and GitLab across FAQ, Capabilities, Config Schema, and Usage.
  - Added GitHub App Quickstart PEM guidance (raw PEM, CI secrets). Docker Compose docs now show correct env variables for GitHub App and GitLab PAT.
  - Fixed README links (removed non-existent Installation page, now pointing to Quickstart and Docker usage).
- Maintain separation of OSS core (self-hosted) from future SaaS/EE work while keeping docs consistent with current capabilities.

## Recent Changes

- Docs:
  - FAQ now reflects GitHub + GitLab support and dashboard terminology (repository issue on either platform).
  - Capabilities: moved “GitHub support” from planned to current; added “Supports both GitHub and GitLab.”
  - Config Schema: removed stale “GitHub coming soon” text in GitLab section; reaffirmed GitHub App auth parameters and env vars.
  - Quickstart GitHub App: added PEM handling note (multiline vs single-line with '\n'); guidance on CI secrets.
  - Docker Compose: added recommended env variables for GitHub App (GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY) and GitLab PAT.
  - README: fixed links to point to Quickstart and Operations Docker page.
- Code (baseline, for awareness):
  - GitHub App flow uses `GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID` (optional), and `GITHUB_APP_PRIVATE_KEY` to generate JWT and obtain installation access token.
  - Validator reads the above env vars via Pydantic defaults.

## Important Caveat (PEM handling)

- Current code expects the private key as a raw PEM string (with real newlines).
- If a CI secret is stored as a single line with literal `\n` characters, normalization to real newlines is NOT implemented in code yet.
  - Impact: single-line `\n` secrets may fail unless the runtime environment expands them to actual newlines.
  - Action: implement a small normalization utility that replaces literal `\\n` with `\n` when `GITHUB_APP_PRIVATE_KEY` appears single-line. Update docs accordingly once shipped.

## Next Steps

- Self-hosted OSS:
  - Implement PEM normalization utility in validator/bootstrap: if key contains `\\n` and no actual newlines, replace with real newlines before JWT signing.
  - Propagate a concise PEM note in:
    - Operations → GitHub Actions (link or admonition to Quickstart GitHub App PEM section).
    - Usage → Onboarding (GitHub path).
  - Validate all doc links after site rebuild; remove stale generated content once deployed.

- SaaS (private `mergebot-ee`, tracked separately):
  - Webhook-driven PR analysis (PR open/sync/reopen; comment commands) with HMAC signature validation.
  - Multi-tenant DB and OAuth/install flows.
  - Admin tasks and scheduling (beyond scope of OSS repo).

## Guidance/Planning

- Keep the Mergebot open source core clean, minimal, and reference-quality.
- Documentation-first: ensure every user-facing flow (GitHub App, GitLab PAT) has a single accurate source of truth and consistent examples.
- Add PEM normalization in code before claiming universal acceptance of single-line `\n` secrets in docs (currently documented with a caveat here).
