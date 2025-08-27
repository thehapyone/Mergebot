# Flow Engine

The Flow Engine orchestrates the Mergebot review pipeline. Tool usage has been externalized from AI crews into a pure Python service layer with retries and backoff to avoid recursive tool loops.

## Overview

- Defines the sequence of crews (agents) and their dependencies.
- Manages state and parallel execution of assessments.
- Aggregates results and applies the approval policy.
- Executes all side-effecting actions (API calls) via the Service Layer, not inside AI crews.

## Execution Sequence

1. PR/MR Details Retrieval (Service Layer)
   - The orchestrator calls the service `mergebot.services.pr_service.get_pull_or_merge_request_details(pr_id)` to fetch a normalized, human-readable summary of the change (metadata, diffs, stats).
   - This step is tool-free in crews and includes exponential backoff with jitter (max 3 attempts) for resilience.

2. Parallel Analysis Crews (AI, Tool-Free)
   - Code Analysis, Complexity, Test, and Risk crews run in parallel using the textual PR/MR details as input.
   - Each crew produces a textual assessment.

3. Impact Evaluation (AI, Tool-Free)
   - Aggregates assessment outputs and approval policy to produce:
     - Overall Impact Score
     - Recommendation (e.g., approve vs hold for review)
     - Report (markdown)

4. Finalization (Service Layer)
   - Orchestrator posts the impact report using `mergebot.services.approval_service.post_impact_report(...)`.
   - If the recommendation is approve, orchestrator calls:
     - `approval_service.approve_change(...)`
     - `approval_service.post_comment(...)` to notify the action taken.
   - No AI agent calls tools directly.

## Service Layer

All tool/API usage is routed through the Service Layer:
- `mergebot/services/common.py`: Retry/backoff decorator, standardized ServiceError.
- `mergebot/services/pr_service.py`: Platform-agnostic PR/MR retrieval (GitHub/GitLab) with retries.
- `mergebot/services/approval_service.py`: Platform-agnostic posting (comments/reports) and approvals with retries.

Benefits:
- Eliminates recursive tool-call loops inside agents.
- Centralized error handling (408/429/5xx) and rate-limit backoff.
- Deterministic orchestration and action execution.

## Outputs and State

- The flow produces:
  - state.impact_assessment: Raw analysis output parsed into fields:
    - score, recommendation, report
  - state.final_decision: Structured, deterministic summary used for downstream systems:
    - recommendation: string
    - impact_score: string
    - action_taken: string (e.g., "Approved" or "Not approved")
    - analysis_link: permalink to the posted report comment (if available)
    - approved: boolean (true when an approval action was taken)
- The run_flow function returns an AnalysisResult with:
  - title, id, impact_score, recommendation, last_reviewed, analysis_link
  - approved (bool), action_taken (string)

This structured shape replaces reliance on a free-form final text blob and makes the result easier to consume by dashboards and external integrations.

## Platform Agnosticism

Existing wrappers (`mergebot/tools/github/api_wrapper.py`, `mergebot/tools/gitlab/api_wrapper.py`) remain platform-specific implementations behind a common interface. The Service Layer routes based on configuration and returns a consistent experience to the flow and crews.

## Extensibility

- Add new analysis crews without any API/tool coupling.
- Extend services for additional actions (labels, merge, issue creation) while keeping crews tool-free.
- Approval policy remains configurable and is consumed by the Impact Evaluator crew.

> See also:
> - Architecture Overview (overview.md)
> - Crews: Code Analysis (crews/code_analysis.md)
> - Publication Crew (crews/publication.md)
