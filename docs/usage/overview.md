# Usage Overview

Mergebot is designed to be run in **ondemand mode** as part of your GitHub Actions, GitLab CI/CD pipeline, or a scheduled job.

- **Ondemand mode**: Analyze open pull or merge requests (PR/MR) in a project on demand (recommended).

## Dashboard: Real-Time PR/MR Tracking & Reruns

Mergebot uses a special "dashboard issue" in your VCS (GitHub or GitLab) to provide a real-time view of all active pull or merge requests (PR/MR), actions, and analytics. This dashboard is automatically created and updated by Mergebot.

**Key features:**

- **Active PR/MR Table:** See all open PRs/MRs, their status, and impact scores.
- **Request a Rerun:** Check a box next to any PR/MR to request Mergebot to reanalyze it. When the CI job runs, Mergebot reads the dashboard, reruns analysis for checked PRs/MRs, and unchecks them after processing.
- **Action Log & Analytics:** Track recent actions and view project analytics directly in the dashboard issue.
- **Transparency:** All updates and decisions are logged for audit and compliance.

**Sample dashboard layout:**
```
## 🧩 Active Pull/Merge Requests (PR/MR)
{{ active_mrs_table }}

### 🔁 Request a Rerun
_Check a box below to ask Mergebot to reanalyze any PR/MR._
{{ rerun_checklist }}

## ✅ Recent Actions
{{ action_log }}

## 📊 Analytics
{{ analytics_table }}
```

> **Current behavior:** Mergebot analyzes every open PR/MR on each run.
> **New:** You can now limit the number of PRs/MRs analyzed per run using the `analysis.max_mrs` config option. See [Configuration Schema](../configuration/config_schema.md#analysis-options).

See [dashboard_layout.md](https://thehapyone.github.io/Mergebot/blob/main/mergebot/dashboard/dashboard_layout.md) for the full template.

- **Webhook mode**: (Experimental) Not actively maintained and may be removed in future releases.

## CI/CD Integration Patterns

See the [CI/CD guides](../operations/docker_compose.md) for ready-to-use templates and best practices for both GitHub Actions and GitLab CI.

- **Per-PR/MR Pipeline**: Run Mergebot as a job in your CI workflow for each pull or merge request pipeline.
- **Dedicated Scheduler Project**: Use a separate project to schedule Mergebot runs across multiple repositories, similar to Renovate's recommended setup.

## Onboarding

- Mergebot requires each project to have a `.mergebot.yml` file.
- If the file is missing, Mergebot will automatically create an onboarding pull or merge request (PR/MR), just like Renovate.

See the sidebar for CLI reference and onboarding details.
