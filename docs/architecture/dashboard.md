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
