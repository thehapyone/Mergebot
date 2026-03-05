# Usage Overview

Mergebot is designed to be run in **ondemand mode** as part of your GitHub Actions, GitLab CI/CD pipeline, or a scheduled job.

- **Ondemand mode**: Analyze open pull or merge requests (PR/MR) in a project on demand (recommended).

## Dashboard: Real-Time PR/MR Tracking & Reruns

Mergebot uses a special "dashboard issue" in your VCS (GitHub or GitLab) to provide a real-time view of all active pull or merge requests (PR/MR), actions, and analytics. This dashboard is automatically created and updated by Mergebot.

**Key features:**

- **Active PR/MR Table:** See all open PRs/MRs, their status, and impact scores.
- **Request a Rerun:** Check a box next to any PR/MR to request Mergebot to reanalyze it. When the CI job runs, Mergebot reads the dashboard, reruns analysis for checked PRs/MRs, and unchecks them after processing.
- **Action Log & Analytics:** Track recent actions and view project analytics directly in the dashboard issue.
- **Token Usage Metrics:** See "Total Tokens Used" for LLM invocations in the project, plus per-crew breakdown, in the dashboard’s analytics section.
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

The analytics section now includes a **Total Tokens Used** metric, which shows the total LLM tokens processed across all PR/MR analyses performed in the current dashboard run. Additional breakdowns by analysis crew may also be visible.

> **Current behavior:** Mergebot analyzes every open PR/MR on each run.
> **New:** You can now limit the number of PRs/MRs analyzed per run using the `analysis.max_mrs` config option. See [Configuration Schema](../configuration/config_schema.md#analysis-options).

See [dashboard_layout.md](https://thehapyone.github.io/Mergebot/blob/main/mergebot/dashboard/dashboard_layout.md) for the full template.

### 🔁 Triggering a new analysis from a PR/MR

Mergebot responds to comment-based commands and mentions in addition to the dashboard checklist. Use any of the following options to queue a new review:

| Trigger | Command | Description |
| --- | --- | --- |
| Comment command | `/mergebot review` | Runs a fresh analysis immediately (ondemand + webhook). |
| Mention | `@mergebot` (or your service account) | Mention Mergebot in any PR/MR comment to request another pass. |
| Dashboard rerun | Check “Request a Rerun” in the Mergebot dashboard | Adds the PR/MR to the rerun queue for the next scan. |

Every impact assessment now ends with a reminder of these commands so authors and reviewers know how to request follow-up help. Mergebot automatically clears the trigger once the rerun completes or the PR/MR is closed/merged.

- **Webhook mode**: (Experimental) Not actively maintained and may be removed in future releases.

## CI/CD Integration Patterns

See the [CI/CD guides](../operations/docker_compose.md) for ready-to-use templates and best practices for both GitHub Actions and GitLab CI.

- **Per-PR/MR Pipeline**: Run Mergebot as a job in your CI workflow for each pull or merge request pipeline.
- **Dedicated Scheduler Project**: Use a separate project to schedule Mergebot runs across multiple repositories, similar to Renovate's recommended setup.

## Onboarding

- Mergebot requires each project to have a `.mergebot.yml` file.
- If the file is missing, Mergebot will automatically create an onboarding pull or merge request (PR/MR), just like Renovate.

See the sidebar for CLI reference and onboarding details.
