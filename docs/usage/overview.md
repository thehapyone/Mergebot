# Usage Overview

Mergebot is designed to be run in **ondemand mode** as part of your GitLab CI/CD pipeline or a scheduled job.

- **Ondemand mode**: Analyze open merge requests in a project on demand (recommended).
- **Dashboard**: View results and analytics in your GitLab project.
- **Webhook mode**: (Experimental) Not actively maintained and may be removed in future releases.

## CI/CD Integration Patterns

- **Per-MR Pipeline**: Run Mergebot as a job in your `.gitlab-ci.yml` for each merge request pipeline.
- **Dedicated Scheduler Project**: Use a separate GitLab project to schedule Mergebot runs across multiple repositories, similar to Renovate's recommended setup.

## Onboarding

- Mergebot requires each project to have a `.mergebot.yml` file.
- If the file is missing, Mergebot will automatically create an onboarding merge request, just like Renovate.

See the sidebar for CLI reference and onboarding details.
