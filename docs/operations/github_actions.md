# Using Mergebot with GitHub Actions

> **Prerequisite:**
> See [Onboarding Guide](../usage/onboarding.md) for GitHub App and secrets setup.

Quickly integrate Mergebot PR/code review automation into your repository with a simple GitHub Actions workflow. The Mergebot container image can be attached directly to a job (mirroring the GitLab examples) so you don’t have to manage `docker run` plumbing yourself.

---

## 1. Pull Request Workflow Example

Add this workflow as `.github/workflows/mergebot.yaml`:

```yaml
name: Mergebot PR Analysis

on:
  pull_request:
    types: [opened, synchronize, reopened]
  workflow_dispatch:

jobs:
  mergebot:
    runs-on: ubuntu-latest
    container:
      image: thehapyone/mergebot:latest
    env:
      GITHUB_APP_ID: ${{ secrets.GITHUB_APP_ID }}
      GITHUB_APP_PRIVATE_KEY: ${{ secrets.GITHUB_APP_PRIVATE_KEY }}
      # AZURE_API_KEY: ${{ secrets.AZURE_API_KEY }}
      # CONFIG_PATH: ${{ github.workspace }}/config-github.yaml
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Run Mergebot
        run: |
          mergebot ondemand --workers 10
```

---

## 2. Scheduled or Multi-Repo Example

For scheduled or batch jobs across multiple repositories:

```yaml
on:
  schedule:
    - cron: '0 2 * * *'
  workflow_dispatch:

jobs:
  batch-mergebot:
    runs-on: ubuntu-latest
    container:
      image: thehapyone/mergebot:latest
    env:
      GITHUB_APP_ID: ${{ secrets.GITHUB_APP_ID }}
      GITHUB_APP_PRIVATE_KEY: ${{ secrets.GITHUB_APP_PRIVATE_KEY }}
      CONFIG_PATH: ${{ github.workspace }}/config-github.yaml
    steps:
      - name: Checkout config repo
        uses: actions/checkout@v4
        with:
          repository: your-org/mergebot-configs
      - name: Run Mergebot for all configured projects
        run: |
          mergebot ondemand \
            --workers 6 \
            --max-concurrency 4
```

---

## Best Practices & Notes

- Use repo/org-level Action secrets for credentials; the container pass-through design mirrors the GitLab CI examples.
- Reference onboarding doc for detailed GitHub App or PAT setup.
- The container runs as root by default; set `container.options` if you need additional capabilities (e.g., corporate CA bundles via mounted volumes).
- Config file: `.mergebot.yml` or `config-github.yaml` ([config docs](../configuration/config_overview.md)). Ensure `repository.projects` lists every repository you want Mergebot to service; no `--project` flag is required.
- For multi-config repos, point `CONFIG_PATH` anywhere under `${{ github.workspace }}` or pass `--config` flags like on GitLab.
- For advanced usage, see [Mergebot on GitHub](https://github.com/thehapyone/Mergebot).

---
