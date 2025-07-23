# Progress

## What Works
- Modular crew system implemented for code analysis, complexity, test, risk, impact evaluation, and publication
- Dashboard system for real-time PR/MR analytics and feedback
- Full integration with both GitHub and GitLab for PR/MR monitoring, onboarding, and feedback
- **Unified, platform-agnostic VCS tool layer:** All crew modules now use tools from `mergebot/tools/common.py` for PR/MR operations, supporting both GitHub and GitLab through a single interface.
- Advanced configuration schema supporting global and per-crew LLMs via LiteLLM (OpenAI, Azure, Anthropic, Google, etc.)
- Comprehensive, browsable documentation site (MkDocs Material) with onboarding, approval policy, and CI/CD guides
- Environment variable best practices for all sensitive credentials
- Automated CI/CD pipeline for linting, style checks, Docker build, Docker Hub publishing, and documentation deployment
- **Configurable PR/MR analysis controls:** Users can now set `analysis.max_mrs` to limit concurrent PR/MR analysis and `analysis.draft_mrs` to control whether Draft/WIP PRs/MRs are analyzed.
- **Refactored draft/WIP detection:** A dedicated helper function (`is_draft_pr`) is used for consistent, maintainable draft/WIP PR/MR detection logic.
- **Documentation and onboarding:** All new analysis options and behaviors are fully documented and reflected in onboarding flows.
- **PR/MR-centric migration complete:** All code, dashboard, and documentation now use PR/MR-centric and VCS-agnostic terminology.

## What's Left to Build
- SaaS dashboard and multi-project management
- More granular crew and LLM configuration options
- Additional CI/CD and deployment guides
- **Pipeline tool integration:** The platform-agnostic pipeline tool is available but not yet used in any crew logic.
- Ongoing documentation and Memory Bank updates as features evolve

## Current Status
- Documentation and onboarding overhaul complete
- Modular, extensible architecture in production use
- **All crew modules now use platform-agnostic VCS tools for PR/MR operations, with no remaining GitLab-specific tool usage.**
- CI/CD and ondemand mode are the recommended and supported workflows
- Automated code quality checks and Docker publishing in place
- **Analysis controls and draft/WIP skipping are now configuration-driven and fully integrated.**
- **All user-facing text, dashboard, and documentation are now PR/MR-centric and VCS-agnostic.**

## Known Issues
- No critical technical issues; pending feature expansion for additional VCS and deployment scenarios

## Evolution of Project Decisions
- Adopted documentation-first workflow using the Memory Bank and MkDocs
- Committed to modular, extensible architecture for all major components
- **Standardized on a unified, platform-agnostic VCS tool layer for all crew operations, supporting both GitHub and GitLab.**
- Standardized on LiteLLM for LLM abstraction and provider flexibility
- Prioritized CI/CD integration and ondemand mode for reliability and scalability
- Automated code quality enforcement and Docker publishing for improved developer experience
- **Moved all PR/MR property logic (e.g., draft/WIP detection) into helper functions for maintainability and clarity.**
