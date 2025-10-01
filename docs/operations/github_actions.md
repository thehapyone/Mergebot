# Using Mergebot with GitHub Actions

> **Prerequisite:**  
> See [Onboarding Guide](../usage/onboarding.md) for GitHub App and secrets setup.

Quickly integrate Mergebot PR/code review automation into your repository with a simple GitHub Actions workflow:

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
    env:
      GITHUB_APP_ID: ${{ secrets.GITHUB_APP_ID }}
      GITHUB_APP_PRIVATE_KEY: ${{ secrets.GITHUB_APP_PRIVATE_KEY }}
      # AZURE_API_KEY: ${{ secrets.AZURE_API_KEY }}
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Pull Mergebot Docker image
        run: docker pull thehapyone/mergebot:latest
      - name: Run Mergebot
        run: |
          docker run --rm \
            -e GITHUB_APP_ID \
            -e GITHUB_APP_PRIVATE_KEY \
            # -e AZURE_API_KEY \
            -v "${{ github.workspace }}:/repo" \
            -w /repo \
            thehapyone/mergebot:latest \
              mergebot ondemand --project="${{ github.repository }}"
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
    strategy:
      matrix:
        repo:
          - owner1/repoA
          - owner2/repoB
    env:
      GITHUB_APP_ID: ${{ secrets.GITHUB_APP_ID }}
      GITHUB_APP_PRIVATE_KEY: ${{ secrets.GITHUB_APP_PRIVATE_KEY }}
    steps:
      - name: Pull Mergebot Docker image
        run: docker pull thehapyone/mergebot:latest
      - name: Run Mergebot on ${{ matrix.repo }}
        run: |
          docker run --rm \
            -e GITHUB_APP_ID \
            -e GITHUB_APP_PRIVATE_KEY \
            -w /tmp \
            thehapyone/mergebot:latest \
              mergebot ondemand --project="${{ matrix.repo }}"
```

---

## Best Practices & Notes

- Use repo/org-level Action secrets for credentials.
- Reference onboarding doc for detailed GitHub App or PAT setup.
- Use the official Docker image for consistency.
- Config file: `.mergebot.yml` or `config-github.yaml` ([config docs](../configuration/config_overview.md)).
- For advanced usage, see [Mergebot on GitHub](https://github.com/thehapyone/Mergebot).

---
