# Quickstart

Get up and running with Mergebot in minutes.

---

> **Platform Support:**  
> Mergebot fully supports **GitHub** and **GitLab** workflows.

---

## 1. Install Mergebot

See [Installation](installation.md) for details.

## 2. Configure Your Repository

- Ensure your GitHub or GitLab project has a valid `.mergebot.yml` configuration file.
- **Create a dedicated service account for Mergebot:**  
  - For GitHub: Create a dedicated GitHub user (e.g., `mergebot`) or use a GitHub App for bot/service account actions.
  - For GitLab: Create a dedicated GitLab user (e.g., `mergebot`) or use a Project Bot.
  - Generate a personal access token for this service account and use it as the `GITHUB_TOKEN` or `GITLAB_PERSONAL_ACCESS_TOKEN` (e.g., store as the `MERGEBOT_TOKEN` CI/CD variable).
  - Add this service account as a member to the relevant project(s) or organization(s) with the minimum required permissions.
  - _Do not use a personal user’s API token_, as this will make it appear that user is performing all Mergebot actions.
  - See [Onboarding](usage/onboarding.md) for details.

## 3. Run Mergebot (Ondemand Mode)

The recommended way to use Mergebot is via **ondemand mode** in your CI/CD pipeline.

See the [CI/CD guides](operations/docker_compose.md) for ready-to-use templates and best practices for both GitHub Actions and GitLab CI.

```bash
# One-shot analysis for a pull or merge request (in a CI job)
mergebot ondemand --project myorg/myrepo
```

Or use Docker:

```bash
docker run --rm thehapyone/mergebot:latest ondemand --project myorg/myrepo
```

You can also schedule Mergebot in a dedicated project to analyze multiple repos, similar to how Renovate is run.

## 4. View Results

- Check your GitHub or GitLab project for the Mergebot Dashboard issue.
- Review auto-approvals, recommendations, and analytics.

---

> **Note:** Webhook mode is experimental and not actively maintained.  
> For advanced configuration, see [Configuration](configuration/config_overview.md).
