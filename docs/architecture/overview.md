# Architecture Overview

Mergebot is built on a modular, extensible architecture using AI-powered "crews" to automate code review and merge decisions.

## Key Components

- **Flow Engine**: Orchestrates the review pipeline using CrewAI.
- **Crews**: Specialized agents for code analysis, complexity, risk, test, impact evaluation, and publication.
- **Dashboard**: Centralized results and analytics, rendered as a repository issue (supports both GitHub and GitLab).
- **Ondemand Runner**: Parallel analysis of multiple pull or merge requests (PR/MR).
- **Configuration**: YAML-based, with support for approval policies and custom workflows.

See the sidebar for deep dives into each component.
