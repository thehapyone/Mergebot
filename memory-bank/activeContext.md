# Active Context

## Current Work Focus

- Finalized the core self-hosted, ondemand Mergebot flow using a GitHub App and PEM string, validated through real use.
- Preparing a clear separation of community/oss codebase and premium/enterprise SaaS offering.

## Recent Changes

- Added robust tokenizer for loading the GitHub App PEM key (multi-line or `\n`).
- Updated all relevant docs to clarify PEM handling and config/ENV.
- Spelled out TODOs for next-gen:
  - Webhook-driven PR analysis and SaaS model.
  - Cloud onboarding and multi-tenant auth.
- Discussed future for hosted app to exist in a private repo (`mergebot-ee`) for Mergebot Cloud/SaaS.

## Next Steps

- **mergebot-ee (private SaaS repo)**
  - New repo for enterprise/cloud codebase: auth, multi-tenant DB layer, user management, webhook & OAuth, admin UI.
  - Inherits/embeds community code as a package/dependency or via internal module sync.
- This public OSS `mergebot` repo focuses on self-host and automation agent, not the full SaaS stack.
- All SaaS-only endpoints, onboarding, advanced admin features, billing belong in private repo.

## Guidance/Planning

- Keep the Mergebot open source core clean, minimal, and reference-quality.
- Build and deploy SaaS/cloud workflow in a separate, nonpublic `mergebot-ee` repository as discussed, ensuring a robust customer/tenant boundary and a clear path for upgrades/extensions.
- Track all cloud/enterprise issues and epics in that private project.
