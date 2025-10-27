# Configuration Schema

Mergebot requires a server/application configuration file (`mergebot/config.yaml`) to run. This file defines the default/global behavior for Mergebot and is always required. When Mergebot runs, it loads this server config and, if a repository config (e.g., `.mergebot.yml`) is present, merges the two to create a unified configuration. If `mergebot/config.yaml` is missing, Mergebot will fail to start.

**Config file location:**
By default, Mergebot looks for the server config at `mergebot/config.yaml` (relative to the working directory).
You can override the location by setting the `CONFIG_PATH` environment variable before running Mergebot:

```bash
export CONFIG_PATH=/path/to/your/config.yaml
mergebot ...
```

This page documents the fields and structure of the Mergebot configuration file (`.mergebot.yml` and `mergebot/config.yaml`).

Looking for a ready-to-edit template? Check out `example-config-gitlab.yaml` and `example-config-github.yaml` in the repository root; they demonstrate multi-project setups with webhook secrets, per-project overrides, and merge guardrails.

## Top-Level Fields

| Field           | Type   | Description                                   |
| --------------- | ------ | --------------------------------------------- |
| llm             | object | Global LLM configuration (provider, model)    |
| repository      | object | Repository configuration (type, gitlab, etc.) |
| crews           | object | Per-crew configuration (optional)             |
| approval_policy | object | Approval policy configuration (optional)      |
| analysis        | object | Analysis options (optional, e.g. MR limits)   |
| telemetry       | object | Telemetry/analytics toggle (optional, see below) |
| merge           | object | Auto-merge configuration (optional)              |

---

## Telemetry

Mergebot supports a simple toggle to enable or disable all OpenTelemetry-based telemetry (including CrewAI telemetry):

```yaml
telemetry:
  enabled: false  # Default: false. Set to true to enable all OpenTelemetry (including CrewAI) telemetry.
```

- When `enabled: false` (or omitted), Mergebot sets the environment variable `OTEL_SDK_DISABLED=true` at startup, disabling all OpenTelemetry instrumentation and telemetry.
- When `enabled: true`, Mergebot unsets `OTEL_SDK_DISABLED` so telemetry is allowed.
- If you set `OTEL_SDK_DISABLED=true` in your environment, this always takes precedence and disables telemetry regardless of config.

**Environment variable override:**
You can force-disable all telemetry by setting `OTEL_SDK_DISABLED=true` in your environment before running Mergebot.

Example:
```bash
export OTEL_SDK_DISABLED=true
mergebot ...
```


## Analysis Options

You can control how many merge requests (MRs) Mergebot will analyze at a time by setting the `analysis.max_mrs` field. If omitted or set to 0, there is no limit.

By default, Mergebot will **skip Draft or WIP MRs**. To analyze them, set `draft_mrs: true`.

```yaml
analysis:
  max_mrs: 10 # Maximum number of MRs to analyze at once (0 or missing = unlimited)
  draft_mrs: false # If true, analyze Draft/WIP MRs. If false (default), skip Draft/WIP MRs.
```

---

## LLM Configuration

Mergebot uses [LiteLLM](https://docs.litellm.ai/docs/) to support a wide range of providers. In the Mergebot config you only specify the model name; LiteLLM picks the provider based on which API keys are present in the environment.

**Global LLM:**

```yaml
llm:
  model: gpt-4o-mini
```

**Per-crew LLM override:**

```yaml
crews:
  CodeAnalysis:
    llm:
      model: gpt-4.1-mini
  ComplexityAnalysis:
    llm:
      model: claude-3-opus-20240229
  TestAnalysis:
    llm:
      model: gemini-1.5-pro
```

If a crew does not specify an LLM, it will use the global model.

### API Keys

**Set API keys as environment variables** (recommended):

- OpenAI: `OPENAI_API_KEY`
- Azure: `AZURE_API_KEY` and `AZURE_API_BASE`
- Anthropic: `ANTHROPIC_API_KEY`
- Google: `GOOGLE_API_KEY`
- See [LiteLLM docs](https://docs.litellm.ai/docs/set_keys) for full details.

---

## Repository Configuration

### GitHub

```yaml
repository:
  type: github
  github:
    api_url: https://api.github.com
    base_branch: main
    # GitHub App authentication (recommended)
    app_id: ${GITHUB_APP_ID}
    installation_id: ${GITHUB_APP_INSTALLATION_ID}   # optional; auto-discovered when omitted
    private_key: ${GITHUB_APP_PRIVATE_KEY}           # raw PEM string or env var
    # Legacy Personal Access Token (not recommended)
    private_token: ${GITHUB_TOKEN}
  projects:
    - path: owner/repo-a
    - path: owner/repo-b
```

- `type`: Must be `github` for GitHub repositories.
- `github`: Required if type is `github`.
- `api_url`: Defaults to `https://api.github.com`.
- `base_branch`: Used when creating onboarding PRs for repositories that do not yet have a `.mergebot.yml`.
- `app_id` / `installation_id` / `private_key`: Prefer GitHub App authentication; values can come from environment variables as shown.
- `private_token`: Optional PAT fallback used only when App credentials are absent.
- Define project-level webhook secrets via `projects[].webhook.secret`.

### GitLab

```yaml
repository:
  type: gitlab
  gitlab:
    url: https://gitlab.example.com/api/v4
    private_token: ${GITLAB_PERSONAL_ACCESS_TOKEN}
    base_branch: main
  projects:
    - path: group/service-a
    - path: group/service-b
```

- `type`: Must be `gitlab`
- `gitlab`: Required if type is `gitlab`
- **Set the GitLab personal access token as the `GITLAB_PERSONAL_ACCESS_TOKEN` environment variable** (recommended).
- Project-level webhook secrets belong under `projects[].webhook.secret`.

---

## Approval Policy

See [Approval Policy](approval_policy.md) for full details.

```yaml
approval_policy:
  threshold: 3.0
  weights:
    CodeAnalysis: 0.4
    ComplexityAnalysis: 0.2
    TestAnalysis: 0.2
    RiskAnalysis: 0.2
```

---

## Multi-Project Configuration (Optional)

For deployments where a single Mergebot instance services multiple repositories, define them under `repository.projects`. Each entry identifies a repository and can override any subset of the global configuration:

```yaml
repository:
  type: gitlab
  gitlab:
    url: https://gitlab.example.com/api/v4
    private_token: ${GITLAB_TOKEN}
    base_branch: main
  projects:
    - path: group/repo-a
      webhook:
        secret: ${GITLAB_WEBHOOK_SECRET_REPO_A}
      overrides:
        analysis:
          max_mrs: 5
        merge:
          enabled: true
          threshold: 2.2
    - path: group/repo-b
      overrides:
        crews:
          CodeAnalysis:
            llm:
              model: gpt-4o-mini
        approval_policy:
          threshold: 2.4
          weights:
            CodeAnalysis: 0.35
            ComplexityAnalysis: 0.2
            TestAnalysis: 0.25
            RiskAnalysis: 0.2
```

Notes:
- Any fields omitted in a project entry fall back to the global configuration defined earlier in the file.
- `webhook.secret` overrides the shared secret used to validate webhook requests for that project. If not provided, ensure the hosting platform supplies the secret (e.g., via environment variables).
- `overrides` can include `analysis`, `merge`, `crews`, and `approval_policy`. These dictionaries are deep-merged with the base config.
- Define at least one project; the orchestrators refuse to start when `repository.projects` is empty.

---

## Merge Configuration

Configure auto-merge behavior. Draft/WIP requests are never merged.

```yaml
merge:
  enabled: false              # Explicit opt-in for auto-merge (default off)
  threshold: null             # If null, falls back to approval_policy.threshold
  strategy: repo_default      # 'repo_default' | 'merge' | 'squash' | 'rebase' (platform support varies)
  rules:
    ci_passed: true               # Require CI to be green
    ci_strict: false              # If true, treat unknown/no CI as failure (default false allows projects without CI)
    no_changes_requested: true    # Block if any review has "changes requested"
    mergeable: true               # Require platform to report mergeable (no conflicts)
    approval_state: true          # Require platform approval state (e.g., required approvals met)
    branch_prefixes:              # Optional allow-list for source branches
      - "feature/"
      - "bugfix/"
```

Notes:
- Threshold requirement: Mergebot only merges when it can evaluate a threshold. Provide `merge.threshold` or rely on `approval_policy.threshold`; if neither is set (or the score can’t be parsed) the merge is skipped with a comment explaining why.
- Draft/WIP: Mergebot will never merge Draft/WIP PRs/MRs (hard rule).
- Threshold fallback: If merge.threshold is not set, Mergebot uses approval_policy.threshold for merge gating.
- Branch allow-list: If rules.branch_prefixes is set, Mergebot only auto-merges when the source branch starts with one of the listed prefixes (e.g., feature/, bugfix/). If unset, all source branches are eligible (subject to other rules).
- CI behavior: With rules.ci_passed: true, failing CI blocks. If no pipelines/checks are configured, CI is treated as unknown and allowed by default. Set rules.ci_strict: true to block when CI is unknown/not configured.
- Comments: Mergebot posts a concise comment whenever it merges or skips, including the impact score, thresholds, and guardrail reasons.

---

## Full Example

```yaml
llm:
  model: gpt-4o-mini

repository:
  type: github
  github:
    api_url: https://api.github.com
    base_branch: main
    app_id: ${GITHUB_APP_ID}
    installation_id: ${GITHUB_APP_INSTALLATION_ID}
    private_key: ${GITHUB_APP_PRIVATE_KEY}
  projects:
    - path: acme/platform-api
      webhook:
        secret: ${PLATFORM_API_WEBHOOK_SECRET}
      overrides:
        merge:
          enabled: true
          threshold: 2.1
          rules:
            ci_passed: true
            ci_strict: true
            branch_prefixes:
              - "feature/"
              - "hotfix/"
        analysis:
          max_mrs: 6
    - path: acme/infra-modules
      overrides:
        crews:
          CodeAnalysis:
            llm:
              model: gpt-4o
        approval_policy:
          threshold: 2.3
          weights:
            CodeAnalysis: 0.35
            ComplexityAnalysis: 0.25
            TestAnalysis: 0.2
            RiskAnalysis: 0.2

crews:
  CodeAnalysis:
    llm:
      model: gpt-4o-mini
  ImpactEvaluator:
    llm:
      model: gpt-4o-mini

approval_policy:
  threshold: 2.5
  weights:
    CodeAnalysis: 0.35
    ComplexityAnalysis: 0.2
    TestAnalysis: 0.25
    RiskAnalysis: 0.2

analysis:
  max_mrs: 10
  draft_mrs: false

merge:
  enabled: false
  strategy: repo_default

telemetry:
  enabled: false
```

---

> **Tip:** All fields are validated. If you provide an invalid agent name or omit a required field, Mergebot will fail fast with a clear error.
> For LLM API keys, always use environment variables for security.
