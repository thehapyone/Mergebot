# Ondemand Runner

The Ondemand Runner enables parallel analysis of multiple pull or merge requests (PR/MR) and updates the dashboard with results.

## Features

- Scans all open PRs/MRs in a project.
- Runs analysis in parallel using async workers.
- Updates the dashboard with new results and analytics.
- Supports periodic mode for continuous monitoring.

## Usage

```bash
CONFIG_PATH=/path/to/config-gitlab.yaml mergebot ondemand --workers 4
```

## Implementation

- Managed by a single, VCS-agnostic Ondemand Runner that works seamlessly with both GitHub and GitLab.
- All PR/MR data is normalized to a common schema for robust, platform-independent dashboard and analytics flows.
- Uses asyncio for concurrency, with repo configuration hydration offloaded to a worker thread so the event loop can fan out across projects without blocking on `.mergebot.yml` fetches.
- Reads the list of projects from `repository.projects` in the server config; no per-run `--project` flag is required.
- Integrates with the Dashboard Manager and Flow Engine.
- Handles errors and preserves previous dashboard data.

> **See also:** [Dashboard](dashboard.md), [Flow Engine](flow.md)
