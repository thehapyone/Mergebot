# Active Context

## Current Work Focus
- Reframing Mergebot as an **impact assessment and automation tool for change requests** (PRs/MRs), with documentation and README updated to emphasize this core value.
- All documentation, onboarding, and user-facing text now highlight Mergebot's workflow: calculate an impact score for each PR/MR, classify as low/medium/high impact, and automate or require review based on policy.
- Migration of all code, documentation, and templates to use PR/MR-centric and VCS-agnostic terminology throughout the project.
- Ensuring all crew modules, dashboard, flow, and ondemand runner are fully platform-agnostic, supporting both GitHub and GitLab through a unified interface.
- Refactored to a single, VCS-agnostic DashboardManager and ondemand runner, with unified PR/MR normalization for all dashboard and analytics flows.
- Ongoing maintenance of documentation-first workflow and Memory Bank as the authoritative source of project context and decisions.

## Recent Changes
- Mergebot's documentation and README now introduce it as an impact assessment and automation tool for change requests (PRs/MRs), with a clear workflow: impact score → classification → automated/manual action.
- The compliance and automation benefits for teams with strict review requirements are now highlighted.
- All crew modules (including publication and pr_processor) now use platform-agnostic tools and PR/MR-centric terminology.
- flow.py, dashboard_manager.py, ondemand_runner.py, and all dashboard and architecture documentation have been updated to use "pull or merge request (PR/MR)" and VCS-agnostic language.
- All previous imports, usages, and documentation of GitLab-specific or MR-centric logic have been removed or refactored.
- The dashboard layout, analytics, and rerun logic are now PR/MR-centric and VCS-agnostic.
- DashboardManager and ondemand_runner refactored to a single, VCS-agnostic implementation, with robust PR/MR normalization and bugfixes for dashboard issue search and rerun request filtering.
- Memory Bank and progress documentation updated to reflect new architecture, workflows, and technical context.

## Next Steps
- Monitor user feedback on the new impact assessment-centric messaging, dashboard, and ondemand runner workflows for both GitHub and GitLab; update documentation as needed.
- Expand documentation and Memory Bank as new features (e.g., pipeline tool usage or additional VCS integrations) are added.
- Continue to enforce documentation-first workflow and CI/CD integration as primary usage patterns.

## Active Decisions & Considerations
- All VCS operations in crews and core logic are now routed through platform-agnostic tools, ensuring maintainability and extensibility.
- The pipeline tool is available for future use, but not currently integrated into any crew logic.
- Helper functions are preferred for encapsulating PR/MR property logic (e.g., draft/WIP detection).
- Documentation and onboarding must always reflect the latest system behavior and configuration options.

## Important Patterns & Preferences
- Modular "crew" system for analysis tasks, with configuration-driven extensibility.
- Platform-agnostic tool layer for all VCS operations, minimizing duplication and maximizing maintainability.
- Helper functions for PR/MR property checks to ensure maintainability and testability.
- MkDocs Material for documentation, with Mermaid diagrams for workflows and architecture.
- Environment variable best practices for all sensitive credentials.
- Automated CI/CD for code quality, Docker builds, and documentation deployment.

## Learnings & Project Insights
- Framing Mergebot as an impact assessment and automation tool for change requests (PRs/MRs) makes its value and workflow clear to all users.
- Centralizing VCS tool logic in a platform-agnostic module reduces duplication and improves maintainability.
- Encapsulating PR/MR property logic in helper functions reduces duplication and improves maintainability.
- Exposing analysis concurrency and draft/WIP handling as config options increases user control and adoption.
- Documentation-first workflow and Memory Bank updates are critical for onboarding and long-term maintainability.
- CI/CD integration and automated documentation deployment improve reliability and developer experience.
