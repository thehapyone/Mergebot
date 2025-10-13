# Dashboard

The Mergebot Dashboard provides a centralized view of pull or merge request (PR/MR) analysis and analytics, rendered as a repository issue (supports both GitHub and GitLab).

## Features

- Tracks all open and recently analyzed pull or merge requests (PR/MR).
- Displays impact scores, recommendations, and review status.
- Shows analytics: PRs/MRs processed, auto-approvals, manual reviews, average time to merge.
- Supports rerun requests and action logs.
- **Shows cumulative LLM token usage:** The analytics section displays "Total Tokens Used" and per-crew token breakdown based on the analyses in the latest dashboard run.

## LLM Token Usage Analytics

The dashboard includes a **Total Tokens Used** statistic showing the sum of all LLM tokens expended by Mergebot’s analysis crews when processing PRs/MRs in a dashboard update run. Values are collected per crew (code_analysis, risk_analysis, etc.) for every PR/MR and are aggregated project-wide in the analytics metrics dict before display.

- **Metric Details:** "Total Tokens Used" is the sum of the `total_tokens` value for each analysis crew, for each PR/MR analyzed during the latest run. A per-crew breakdown is also visible as "Tokens Used (crewname)".
- **Retention:** The metric reflects token usage for the *current dashboard scan*: it is not cumulative across historical runs, but always up-to-date with the latest batch analyzed.
- **Extensibility:** The system supports adding further fine-grained LLM usage tracking or historical retention via additional dashboard markers or data artifacts.
- **Implementation:** Usage metrics are gathered in per-PR/MR flow state, made available for aggregation in the dashboard runner, and pushed into the analytics dict for display.

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
