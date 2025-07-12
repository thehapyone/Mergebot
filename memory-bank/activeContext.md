# Active Context

## Current Work Focus
- Comprehensive overhaul and migration of Mergebot documentation to a structured, browsable MkDocs site
- Integration of advanced configuration schema documentation, including multi-provider LLM support via LiteLLM
- Improved onboarding, approval policy, and CI/CD usage documentation
- Memory Bank update to reflect new architecture, workflows, and technical context

## Recent Changes
- All documentation migrated to a modular MkDocs site with navigation, search, and Mermaid diagrams
- Legacy docs (ONBOARDING.md, APPROVAL_POLICY.md) removed in favor of new, integrated pages
- Configuration schema documentation now covers global and per-crew LLM, provider selection, and environment variable best practices
- Onboarding and approval policy pages enhanced with diagrams and improved clarity

## Next Steps
- Continue to iterate on documentation as new features (e.g., GitHub support) are added
- Expand CI/CD and deployment guides as user needs evolve
- Maintain Memory Bank as the authoritative source of project context and decisions

## Active Decisions & Considerations
- Documentation-first workflow: all context and decisions are captured in the Memory Bank and docs site
- Focus on ondemand mode and CI/CD integration as the primary usage pattern
- LiteLLM as the abstraction layer for all LLM providers, with environment variable-based API key management

## Important Patterns & Preferences
- Modular "crew" system for analysis tasks, with configuration-driven extensibility
- MkDocs Material for documentation, with Mermaid diagrams for workflows and architecture
- Environment variable best practices for all sensitive credentials

## Learnings & Project Insights
- Early investment in documentation and onboarding accelerates adoption and reduces support burden
- Abstraction over LLM providers (via LiteLLM) enables rapid support for new models and vendors
- CI/CD integration is the most reliable and scalable way to run Mergebot in production
