# Dashboard

The Mergebot Dashboard provides a centralized view of merge request analysis and analytics, rendered as a GitLab issue.

## Features

- Tracks all open and recently analyzed merge requests.
- Displays impact scores, recommendations, and review status.
- Shows analytics: MRs processed, auto-approvals, manual reviews, average time to merge.
- Supports rerun requests and action logs.

## Implementation

- Managed by the Dashboard Manager.
- Uses Markdown tables and special comment tags for metadata.
- Updates automatically after each ondemand or webhook run.

> **See also:** [Ondemand Runner](ondemand_runner.md), [Flow Engine](flow.md)
