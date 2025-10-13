# System Patterns

## System Architecture Overview
Mergebot is designed as a modular, extensible system for automated pull or merge request (PR/MR) analysis and management. The architecture is centered around the concept of "crews"—independent, pluggable analysis modules that each handle a specific aspect of PR/MR review.

### Key Components
- **Core Engine**: Orchestrates the workflow, manages PR/MR lifecycle, and coordinates crews.
- **Crews**: Modular analysis units (e.g., code analysis, risk analysis, test coverage, impact evaluation, publication).
- **VCS Integration Layer**: Handles communication with GitHub, GitLab, and other VCS APIs for PR/MR data, status updates, and feedback.
- **Dashboard**: Provides real-time monitoring and insights into PR/MR status and system activity via a unified, VCS-agnostic DashboardManager.
- **LiteLLM Integration**: Abstracts LLM provider selection, supporting OpenAI, Azure, Anthropic, Google, and more.
- **Memory Bank**: Centralized documentation and context management system.
- **MkDocs Documentation**: Comprehensive, browsable documentation site with onboarding, approval policy, and CI/CD guides.

## Key Technical Decisions
- Modular crew-based architecture for extensibility and maintainability
- Python as the primary implementation language
- GitHub and GitLab as primary VCS integration targets, with roadmap for additional VCS support
- LiteLLM as the LLM abstraction layer for multi-provider support
- Documentation-first workflow using the Memory Bank and MkDocs Material

## Design Patterns in Use
- **Modular Plugin Pattern**: Each crew is a self-contained module with a defined interface.
- **Orchestrator Pattern**: The core engine acts as an orchestrator, invoking crews as needed.
- **Unified VCS-Agnostic Dashboard Pattern**: A single DashboardManager class abstracts all dashboard operations for both GitHub and GitLab, selecting the correct API wrapper at runtime.
- **PR/MR Normalization Pattern**: All PR/MR objects are normalized to a common schema (e.g., `iid`, `web_url`, `title`) for dashboard, analytics, and analysis flows, ensuring platform-agnostic logic throughout.
- **Cross-Crew Analytics Aggregation Pattern**: Usage metrics (e.g., LLM tokens consumed) are captured individually by each crew, then aggregated project-wide via the orchestrator for display in the dashboard. This enables extensible analytics—such as "Total Tokens Used" and per-crew statistics—for transparency and cost management.
- **Configuration-Driven Behavior**: System behavior and crew activation are controlled via configuration files, supporting global and per-crew LLM settings.
- **Audit Logging**: All actions and decisions are logged for traceability.
- **Environment Variable Best Practices**: All sensitive credentials (LLM API keys, GitLab tokens) are managed via environment variables.

## Component Relationships
- The core engine invokes crews in a configurable sequence for each PR/MR.
- Both GitHub and GitLab adapters implement `get_pipeline_details`. The GitHub implementation is fully refactored: modular helpers for fetching jobs, job summary, and log window slicing, with step-precise log parsing for errors.
- In PR/MR analysis flow, the pipeline summary is automatically formatted, focused, and robust to Actions log structure.
- The `GetPipelineDetailsTool` enables direct retrieval of pipeline/run details for either platform, in CLI, API, and automation.
- Crews operate independently but may share context via the Memory Bank.
- The unified DashboardManager aggregates and displays results from all crews and system actions, using normalized PR/MR data for both GitHub and GitLab.
- Documentation and onboarding are tightly integrated with the system for rapid adoption.

## Critical Implementation Paths
- PR/MR event triggers or CI/CD pipeline → Core engine → Crew execution → get_pipeline_details (GitHub/GitLab) → PR summary aggregation (pipeline/jobs/errors) → VCS update → Dashboard update → Memory Bank documentation

## Session Lock Pattern

A stateless, project-scoped session lock prevents concurrent Mergebot runs on the same repository.

- Persistence: Lock is stored inside the repository’s Dashboard issue under a single “Active Session” header, with content bounded by `<!-- marker:MERGEBOT_SESSION_LOCK -->` markers. Only the content between markers is updated; the header is owned by the template.
- TTL & Heartbeat: Default TTL is 10 minutes (600s). A heartbeat extends `expires_at` periodically (~200s by default) while a session is active to avoid mid-run expiry.
- Owner Identity: Uses `hostname-pid-uuid` for traceability.
- Acquisition Algorithm: Optimistic write-then-verify with a nonce.
  1) Read dashboard and parse lock JSON.
  2) If an unexpired lock exists with a different owner, skip (busy).
  3) Otherwise, write a lock with a unique nonce and immediate `expires_at`.
  4) Re-read; proceed only if our nonce is present (we won the race).
- Release: On completion, if we still own the lock (owner+nonce match), replace the lock section with a placeholder (no active lock).
- Normalized Placement: If markers exist but are out of place, the coordinator rewrites the section to reside under the “Active Session” area before “Analytics” within the main dashboard region.
- Integration Points:
  - Ondemand Runner: Acquire at the start of `run_once()`. If busy, skip the run. Otherwise, start heartbeat and release in a finally step.
  - Webhook Server: `analyze_with_session_lock()` wraps `run_flow(...)` so webhook-triggered runs respect the same project session lock.
- Failure Safety: If the process crashes, the lock expires automatically after TTL, allowing future sessions to proceed.
- Rationale: Project-level session lock avoids duplicate dashboard updates and duplicated PR/MR comments from overlapping runs, with zero external infrastructure.
