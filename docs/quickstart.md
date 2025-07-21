# Quickstart

Get up and running with Mergebot in minutes.

---

> **Platform Support:**  
> Mergebot currently supports **GitLab** only.  
> **GitHub support is planned for upcoming releases.**

---

## 1. Install Mergebot

See [Installation](installation.md) for details.

## 2. Configure Your Repository

- Ensure your GitLab project has a valid `.mergebot.yml` configuration file.
- **Create a dedicated GitLab service account for Mergebot:**  
  - It is strongly recommended to create a dedicated GitLab user (e.g., `mergebot`) to act as a bot/service account.
  - Generate a personal access token for this service account and use it as the `GITLAB_PERSONAL_ACCESS_TOKEN` (e.g., store as the `MERGEBOT_TOKEN` CI/CD variable).
  - Add this service account as a member to the relevant project(s) or group(s) with the minimum required permissions.
  - _Do not use a personal user’s API token_, as this will make it appear that user is performing all Mergebot actions.
  - **Alternative:** You may use a [Project Bot](https://docs.gitlab.com/ee/user/project/bot_users.html), but note that project bots cannot be reused across multiple projects. For most organizations, a dedicated service account at the instance or group level is preferred.
- See [Onboarding](usage/onboarding.md) for details.

## 3. Run Mergebot (Ondemand Mode)

The recommended way to use Mergebot is via **ondemand mode** in your CI/CD pipeline.

See the [GitLab CI guide](operations/gitlab_ci.md) for ready-to-use `.gitlab-ci.yml` templates and best practices.

```bash
# One-shot analysis for a merge request (in a GitLab CI job)
mergebot ondemand --project mygroup/myrepo
```

Or use Docker:

```bash
docker run --rm thehapyone/mergebot:latest ondemand --project mygroup/myrepo
```

You can also schedule Mergebot in a dedicated GitLab project to analyze multiple repos, similar to how Renovate is run.

## 4. View Results

- Check your GitLab project for the Mergebot Dashboard issue.
- Review auto-approvals, recommendations, and analytics.

---

> **Note:** Webhook mode is experimental and not actively maintained.  
> For advanced configuration, see [Configuration](configuration/config_overview.md).
