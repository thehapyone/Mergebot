# Product Context

## Why Mergebot Exists
The core idea behind Mergebot is to provide **automated impact assessment for every change request** (pull or merge request, PR/MR). By calculating an impact score for each PR/MR, Mergebot enables teams to:
- Classify changes as low, medium, or high impact
- Automate approvals and merges for low-impact changes, accelerating delivery without breaking compliance
- Require human review for high-impact changes, ensuring that risky or complex changes always get the attention they deserve

This approach allows teams to automate routine approvals, maintain high standards, and meet compliance requirements—without burning out reviewers or slowing down delivery.

Modern software teams face increasing pressure to deliver high-quality code rapidly. Manual code review processes are time-consuming, inconsistent, and often fail to catch subtle issues or risks. As teams grow and codebases scale, the challenge of maintaining code quality and review velocity intensifies.

## Problems Solved
- Reduces manual effort in reviewing pull or merge requests (PR/MR)
- Identifies code quality, risk, and test coverage issues automatically
- Provides actionable, consistent feedback to developers
- Accelerates the integration of safe, high-quality code
- Increases transparency and traceability in the review process
- Simplifies onboarding and configuration with a comprehensive docs site and onboarding workflow

## How Mergebot Should Work
- Integrates directly with GitHub, GitLab, and other VCS to monitor and process PRs/MRs
- For each PR/MR, surfaces a detailed CI pipeline summary (GitHub Actions or GitLab), making job/runs output, failures, and errors visible and comparable across providers
- Runs a series of automated "crews" (modular analysis components) on each PR/MR
- Aggregates results and generates clear, actionable feedback
- Recommends approval or further action based on analysis and approval policy
- Maintains an auditable log of all actions and decisions
- Provides a dashboard for real-time monitoring and insights
- Supports advanced LLM configuration via LiteLLM, enabling use of OpenAI, Azure, Anthropic, Google, and more

## User Experience Goals
- Seamless integration with existing GitHub, GitLab, and CI/CD workflows
- Minimal manual intervention required from developers and reviewers
- Fast, reliable feedback on every PR/MR
- Clear, actionable recommendations and transparency in decision-making, with unified CI pipeline/job summaries always displayed
- Easy extensibility for new analysis modules, LLM providers, and workflows
- Comprehensive, browsable documentation for onboarding and troubleshooting

## Roadmap & Future Vision
- Enhanced CI/CD and deployment guides
- More granular crew and LLM configuration options
- SaaS dashboard and multi-project management
