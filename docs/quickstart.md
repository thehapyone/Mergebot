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
- See [Onboarding](usage/onboarding.md) for details.

## 3. Run Mergebot (Ondemand Mode)

The recommended way to use Mergebot is via **ondemand mode** in your CI/CD pipeline.

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
