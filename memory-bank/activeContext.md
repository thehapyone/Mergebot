# Active Context

## Current Work Focus
- Implementation of advanced MR analysis controls: max MRs per run and draft/WIP MR skipping, both configurable via `analysis` section in config.
- Refactoring of MR draft/WIP detection logic to use a dedicated helper function for maintainability and clarity.
- Comprehensive update of onboarding and configuration documentation to reflect new analysis options and behaviors.
- Ongoing maintenance of documentation-first workflow and Memory Bank as the authoritative source of project context and decisions.

## Recent Changes
- Added `analysis.max_mrs` and `analysis.draft_mrs` config options to control MR analysis concurrency and draft/WIP MR handling.
- Refactored MR draft/WIP detection to use a single helper function (`is_draft_mr`) for consistent, testable logic.
- Updated onboarding and configuration docs to clearly document new analysis options, including default behaviors and override instructions.
- All code, schema, and onboarding now reference `draft_mrs` for clarity and consistency.
- Memory Bank and progress documentation updated to reflect new architecture, workflows, and technical context.

## Next Steps
- Monitor user feedback on new analysis controls and draft/WIP MR handling.
- Expand documentation and Memory Bank as new features (e.g., GitHub support) are added.
- Continue to enforce documentation-first workflow and CI/CD integration as primary usage patterns.

## Active Decisions & Considerations
- Default behavior is to skip draft/WIP MRs unless `analysis.draft_mrs: true` is set.
- All MR analysis concurrency and filtering is now configuration-driven for maximum flexibility.
- Helper functions are preferred for encapsulating MR property logic (e.g., draft/WIP detection).
- Documentation and onboarding must always reflect the latest system behavior and configuration options.

## Important Patterns & Preferences
- Modular "crew" system for analysis tasks, with configuration-driven extensibility.
- Helper functions for MR property checks to ensure maintainability and testability.
- MkDocs Material for documentation, with Mermaid diagrams for workflows and architecture.
- Environment variable best practices for all sensitive credentials.
- Automated CI/CD for code quality, Docker builds, and documentation deployment.

## Learnings & Project Insights
- Encapsulating MR property logic in helper functions reduces duplication and improves maintainability.
- Exposing analysis concurrency and draft/WIP handling as config options increases user control and adoption.
- Documentation-first workflow and Memory Bank updates are critical for onboarding and long-term maintainability.
- CI/CD integration and automated documentation deployment improve reliability and developer experience.
