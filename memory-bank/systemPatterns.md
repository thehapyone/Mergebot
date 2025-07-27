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
- **Configuration-Driven Behavior**: System behavior and crew activation are controlled via configuration files, supporting global and per-crew LLM settings.
- **Audit Logging**: All actions and decisions are logged for traceability.
- **Environment Variable Best Practices**: All sensitive credentials (LLM API keys, GitLab tokens) are managed via environment variables.

## Component Relationships
- The core engine invokes crews in a configurable sequence for each PR/MR.
- Crews operate independently but may share context via the Memory Bank.
- The unified DashboardManager aggregates and displays results from all crews and system actions, using normalized PR/MR data for both GitHub and GitLab.
- Documentation and onboarding are tightly integrated with the system for rapid adoption.

## Critical Implementation Paths
- PR/MR event triggers or CI/CD pipeline → Core engine → Crew execution → Feedback aggregation → VCS update → Dashboard update → Memory Bank documentation
