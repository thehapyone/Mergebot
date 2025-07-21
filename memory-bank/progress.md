# Progress

## What Works
- Modular crew system implemented for code analysis, complexity, test, risk, impact evaluation, and publication
- Dashboard system for real-time MR analytics and feedback
- Full integration with GitLab for MR monitoring, onboarding, and feedback
- Advanced configuration schema supporting global and per-crew LLMs via LiteLLM (OpenAI, Azure, Anthropic, Google, etc.)
- Comprehensive, browsable documentation site (MkDocs Material) with onboarding, approval policy, and CI/CD guides
- Environment variable best practices for all sensitive credentials
- Automated CI/CD pipeline for linting, style checks, Docker build, Docker Hub publishing, and documentation deployment
- **Configurable MR analysis controls:** Users can now set `analysis.max_mrs` to limit concurrent MR analysis and `analysis.draft_mrs` to control whether Draft/WIP MRs are analyzed.
- **Refactored draft/WIP detection:** A dedicated helper function (`is_draft_mr`) is used for consistent, maintainable draft/WIP MR detection logic.
- **Documentation and onboarding:** All new analysis options and behaviors are fully documented and reflected in onboarding flows.

## What's Left to Build
- GitHub and other VCS platform support
- SaaS dashboard and multi-project management
- More granular crew and LLM configuration options
- Additional CI/CD and deployment guides
- Ongoing documentation and Memory Bank updates as features evolve

## Current Status
- Documentation and onboarding overhaul complete
- Modular, extensible architecture in production use
- CI/CD and ondemand mode are the recommended and supported workflows
- Automated code quality checks and Docker publishing in place
- **Analysis controls and draft/WIP skipping are now configuration-driven and fully integrated.**

## Known Issues
- No critical technical issues; pending feature expansion for additional VCS and deployment scenarios

## Evolution of Project Decisions
- Adopted documentation-first workflow using the Memory Bank and MkDocs
- Committed to modular, extensible architecture for all major components
- Standardized on LiteLLM for LLM abstraction and provider flexibility
- Prioritized CI/CD integration and ondemand mode for reliability and scalability
- Automated code quality enforcement and Docker publishing for improved developer experience
- **Moved all MR property logic (e.g., draft/WIP detection) into helper functions for maintainability and clarity.**
