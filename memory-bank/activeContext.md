# Active Context

## Current Work Focus
- Migration of all crew modules to use platform-agnostic VCS tools from `mergebot/tools/common.py`, supporting both GitHub and GitLab through a unified interface.
- Validation and cleanup of all crew code to remove legacy GitLab-specific tool usage.
- Ongoing maintenance of documentation-first workflow and Memory Bank as the authoritative source of project context and decisions.

## Recent Changes
- All crew modules (including publication and mr_processor) now import and use platform-agnostic tools (`PullRequestTool`, `PullRequestCommentTool`, `PullRequestApprovalTool`) from `mergebot/tools/common.py`.
- All previous imports and usages of GitLab-specific tool classes have been removed from the codebase.
- The pipeline tool (`GitlabPipelineTool`) is available in the common tools module, but is not currently used in any crew implementation; pipeline information is referenced in configuration only.
- The codebase is now unified for GitHub and GitLab, with a single code path for VCS operations.
- Memory Bank and progress documentation updated to reflect new architecture, workflows, and technical context.

## Next Steps
- Monitor user feedback on the unified VCS tool interface and update documentation as needed.
- Expand documentation and Memory Bank as new features (e.g., pipeline tool usage or additional VCS integrations) are added.
- Continue to enforce documentation-first workflow and CI/CD integration as primary usage patterns.

## Active Decisions & Considerations
- All VCS operations in crews are now routed through platform-agnostic tools, ensuring maintainability and extensibility.
- The pipeline tool is available for future use, but not currently integrated into any crew logic.
- Helper functions are preferred for encapsulating MR property logic (e.g., draft/WIP detection).
- Documentation and onboarding must always reflect the latest system behavior and configuration options.

## Important Patterns & Preferences
- Modular "crew" system for analysis tasks, with configuration-driven extensibility.
- Platform-agnostic tool layer for all VCS operations, minimizing duplication and maximizing maintainability.
- Helper functions for MR property checks to ensure maintainability and testability.
- MkDocs Material for documentation, with Mermaid diagrams for workflows and architecture.
- Environment variable best practices for all sensitive credentials.
- Automated CI/CD for code quality, Docker builds, and documentation deployment.

## Learnings & Project Insights
- Centralizing VCS tool logic in a platform-agnostic module reduces duplication and improves maintainability.
- Encapsulating MR property logic in helper functions reduces duplication and improves maintainability.
- Exposing analysis concurrency and draft/WIP handling as config options increases user control and adoption.
- Documentation-first workflow and Memory Bank updates are critical for onboarding and long-term maintainability.
- CI/CD integration and automated documentation deployment improve reliability and developer experience.
