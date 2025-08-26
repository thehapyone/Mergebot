# Publication (Removed in v0.1.0)

This crew has been removed. Finalization is now performed directly by the Flow Engine via the Service Layer, which executes all external actions (posting comments, approvals) with retries and backoff.

## Current Responsibilities (handled by services)

- Post the formatted impact assessment report (comment) to the PR/MR.
- If the recommendation indicates approval, approve the PR/MR and post an action confirmation comment.

These are executed by:
- mergebot.services.approval_service.post_impact_report(...)
- mergebot.services.approval_service.approve_change(...)
- mergebot.services.approval_service.post_comment(...)

## Rationale

- Eliminates recursive tool-call loops within AI agents.
- Centralizes error handling with exponential backoff and jitter (max 3 attempts).
- Keeps AI crews reasoning-only and side-effect free.

> See also:
> - Flow Engine (../flow.md)
> - Service Layer overview in docs/architecture/flow.md
