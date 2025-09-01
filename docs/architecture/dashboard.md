# Dashboard

The Mergebot Dashboard provides a centralized view of pull or merge request (PR/MR) analysis and analytics, rendered as a repository issue (supports both GitHub and GitLab).

## Features

- Tracks all open and recently analyzed pull or merge requests (PR/MR).
- Displays impact scores, recommendations, and review status.
- Shows analytics: PRs/MRs processed, auto-approvals, manual reviews, average time to merge.
- Supports rerun requests and action logs.

## Implementation

- Managed by a single, VCS-agnostic Dashboard Manager that works seamlessly with both GitHub and GitLab.
- All PR/MR data is normalized to a common schema for robust, platform-independent analytics and reporting.
- Uses Markdown tables and special comment tags for metadata.
- Updates automatically after each ondemand or webhook run.

> **See also:** [Ondemand Runner](ondemand_runner.md), [Flow Engine](flow.md)

## Project-level Session Lock

Mergebot prevents duplicate project runs by maintaining a stateless, project-scoped “session lock” inside the Dashboard issue body.

- Location: within the “Active Session” section, bounded by `<!-- marker:MERGEBOT_SESSION_LOCK -->` markers.
- Format: a fenced JSON block persisted in the issue body.
- Default TTL: 10 minutes (auto-extends via heartbeat during a running session).
- Owner identity: derived from `hostname-pid-uuid`.

Example lock payload (rendered in the dashboard as fenced code):

```json
{"version":1,"updated_at":"2025-09-01T11:23:45Z","lock":{"owner":"host-1-uuid","started_at":"2025-09-01T11:20:00Z","expires_at":"2025-09-01T11:30:00Z","nonce":"abc123"}}
```

Behavior:
- On acquisition, Mergebot writes the lock JSON and immediately re-reads to verify it “won” the race (nonce check).
- Only one project session (ondemand run or webhook-triggered run) can proceed at a time per repository.
- If a process crashes, the lock expires automatically after the TTL and future sessions can proceed.
- The dashboard renderer always preserves the lock section across full re-renders and places it under the single “Active Session” header (no duplicate headers).
