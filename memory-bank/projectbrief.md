# Project Brief

## Project Name
Mergebot

## Purpose
Mergebot is an automated system designed to streamline, analyze, and manage code pull or merge requests (PR/MR) in software development projects. Its core workflow is to:
- Calculate an impact score for every change request (PR/MR)
- Classify changes as low, medium, or high impact
- Automate approvals and merges for low-impact changes, while requiring human review for high-impact changes

This enables teams to automate routine approvals, maintain high standards, and meet compliance requirements—without burning out reviewers or slowing down delivery. Mergebot aims to improve code quality, reduce manual review effort, and accelerate the integration process.

## Core Requirements
- Automate the analysis of pull or merge requests (PR/MR) for code quality, risk, and impact.
- Integrate with both GitHub and GitLab (and other VCS platforms in the future).
- Provide actionable feedback and approval recommendations for each PR/MR.
- Support extensible "crews" (modular analysis components) for different review tasks (e.g., code analysis, risk analysis, test coverage).
- Maintain a clear, auditable record of all actions and decisions.
- Offer a dashboard for monitoring PR/MR status and system activity.
- Enable advanced LLM configuration via LiteLLM, supporting OpenAI, Azure, Anthropic, Google, and more.
- Provide a comprehensive, browsable documentation site for onboarding, configuration, and troubleshooting.

## Goals
- Reduce manual review workload for development teams.
- Increase consistency and reliability of code reviews.
- Enable rapid, safe integration of code changes.
- Provide transparency and traceability for all automated decisions.
- Make onboarding and configuration as seamless as possible.

## Scope
- Focus on GitHub and GitLab integration and ondemand mode as the primary usage pattern.
- Modular architecture to allow easy addition of new analysis crews and LLM providers.
- Initial implementation targets Python codebases, with future extensibility.

## Out of Scope
- Direct support for non-GitHub/GitLab platforms (unless specified in future updates).
- Manual code review features (focus is on automation).
- Non-code artifact analysis (e.g., binary files, images).

## Stakeholders
- Software development teams
- DevOps engineers
- Project managers
- Quality assurance teams

## Success Criteria
- Demonstrated reduction in manual review time.
- High accuracy of automated review feedback.
- Positive adoption and feedback from target users.
- High-quality, up-to-date documentation and onboarding experience.
