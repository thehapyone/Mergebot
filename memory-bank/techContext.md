# Technical Context

## Technologies Used
- **Programming Language**: Python (primary)
- **Version Control System**: GitHub and GitLab (fully supported); extensible to other VCS platforms
- **Containerization**: Docker (for deployment and local development)
- **Configuration**: YAML files for crew and system configuration
- **LLM Abstraction**: [LiteLLM](https://docs.litellm.ai/docs/) for multi-provider LLM support (OpenAI, Azure, Anthropic, Google, etc.)
- **Documentation**: MkDocs Material (Markdown, Mermaid diagrams, CI/CD integration)
- **Dependency Management**: Poetry (for all dev and runtime dependencies)

## Development Setup
- Python environment managed via Poetry
- Docker and docker-compose for local development and deployment
- Modular directory structure for crews, tools, and dashboard components
- All configuration and documentation files stored in version control
- Environment variable best practices for all sensitive credentials (LLM API keys, VCS tokens)

## Technical Constraints
- Initial implementation targets Python codebases and supports both GitHub and GitLab integration
- System must be extensible to support new crews, LLM providers, and analysis modules
- All actions and decisions must be auditable and traceable
- Documentation and onboarding must be comprehensive and easy to maintain

## Dependencies
- Python standard library
- Third-party libraries for GitHub and GitLab API integration, YAML parsing, LiteLLM, MkDocs, and web server functionality (see pyproject.toml for details)
- Docker for containerization

## Tool Usage Patterns
- Modular "crew" system: each crew is a self-contained analysis module
- Configuration-driven: system and crew behavior controlled via YAML files, supporting global and per-crew LLM settings
- Documentation-first: all context, decisions, and progress tracked in the Memory Bank and docs site
- CI/CD integration: ondemand mode is the recommended and supported workflow for production use
