# Usage Overview

Mergebot is designed to be run in **ondemand mode** as part of your GitLab CI/CD pipeline or a scheduled job.

- **Ondemand mode**: Analyze open merge requests in a project on demand (recommended).

## Dashboard: Real-Time MR Tracking & Reruns

Mergebot uses a special "dashboard issue" in your VCS (e.g., GitLab) to provide a real-time view of all active merge requests, actions, and analytics. This dashboard is automatically created and updated by Mergebot.

**Key features:**

- **Active MR Table:** See all open MRs, their status, and impact scores.
- **Request a Rerun:** Check a box next to any MR to request Mergebot to reanalyze it. When the CI job runs, Mergebot reads the dashboard, reruns analysis for checked MRs, and unchecks them after processing.
- **Action Log & Analytics:** Track recent actions and view project analytics directly in the dashboard issue.
- **Transparency:** All updates and decisions are logged for audit and compliance.

**Sample dashboard layout:**
```
## 🧩 Active Merge Requests
{{ active_mrs_table }}

### 🔁 Request a Rerun
_Check a box below to ask Mergebot to reanalyze any MR._
{{ rerun_checklist }}

## ✅ Recent Actions
{{ action_log }}

## 📊 Analytics
{{ analytics_table }}
```

> **Current behavior:** Mergebot analyzes every open MR/PR on each run.
> **New:** You can now limit the number of MRs analyzed per run using the `analysis.max_mrs` config option. See [Configuration Schema](../configuration/config_schema.md#analysis-options).

See [dashboard_layout.md](https://thehapyone.github.io/Mergebot/blob/main/mergebot/dashboard/dashboard_layout.md) for the full template.

- **Webhook mode**: (Experimental) Not actively maintained and may be removed in future releases.

## CI/CD Integration Patterns

See the [GitLab CI guide](../operations/gitlab_ci.md) for ready-to-use templates and best practices.

- **Per-MR Pipeline**: Run Mergebot as a job in your `.gitlab-ci.yml` for each merge request pipeline.
- **Dedicated Scheduler Project**: Use a separate GitLab project to schedule Mergebot runs across multiple repositories, similar to Renovate's recommended setup.

## Onboarding

- Mergebot requires each project to have a `.mergebot.yml` file.
- If the file is missing, Mergebot will automatically create an onboarding merge request, just like Renovate.

See the sidebar for CLI reference and onboarding details.
