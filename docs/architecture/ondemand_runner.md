# Ondemand Runner

The Ondemand Runner enables parallel analysis of multiple pull or merge requests (PR/MR) and updates the dashboard with results.

## Features

- Scans all open PRs/MRs in a project.
- Runs analysis in parallel using async workers.
- Updates the dashboard with new results and analytics.
- Supports periodic mode for continuous monitoring.

## Usage

```bash
mergebot ondemand --project mygroup/myrepo --workers 4
```

## Implementation

- Uses asyncio for concurrency.
- Integrates with the Dashboard Manager and Flow Engine.
- Handles errors and preserves previous dashboard data.

> **See also:** [Dashboard](dashboard.md), [Flow Engine](flow.md)
