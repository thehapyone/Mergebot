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

## Top-Level Fields

| Field           | Type   | Description                                   |
| --------------- | ------ | --------------------------------------------- |
| llm             | object | Global LLM configuration (provider, model)    |
| repository      | object | Repository configuration (type, gitlab, etc.) |
| crews           | object | Per-crew configuration (optional)             |
| approval_policy | object | Approval policy configuration (optional)      |
| analysis        | object | Analysis options (optional, e.g. MR limits)   |
| telemetry       | object | Telemetry/analytics toggle (optional, see below) |

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

Mergebot uses [LiteLLM](https://docs.litellm.ai/docs/) to support a wide range of LLM providers, including OpenAI, Azure, Anthropic, Google, and more.

You can set a global LLM provider/model, and override it per crew.

**Global LLM:**

```yaml
llm:
  model: gpt-4
  # provider: openai  # (optional, defaults to openai)
```

**Per-crew LLM override:**

```yaml
crews:
  CodeAnalysis:
    llm:
      model: gpt-4-turbo
      provider: openai
  ComplexityAnalysis:
    llm:
      model: anthropic.claude-3-opus-20240229
      provider: anthropic
  TestAnalysis:
    llm:
      model: gemini-pro
      provider: google
```

If a crew does not specify an LLM, it will use the global model.

### Supported Providers

- `openai` (default)
- `azure`
- `anthropic`
- `google`
- ...and others supported by LiteLLM

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
    base_branch: main
    # GitHub App authentication (recommended)
    app_id: 123456                # GitHub App ID (int or ENV: GITHUB_APP_ID)
    installation_id: 987654       # Installation ID (int, optional; ENV: GITHUB_APP_INSTALLATION_ID)
    private_key: <raw PEM value> # raw PEM (ENV: GITHUB_APP_PRIVATE_KEY)
    # Legacy Personal Access Token (not recommended)
    private_token: YOUR_TOKEN     # (not recommended, use env var)
```

- `type`: Must be `github` for GitHub repositories.
- `github`: Required if type is `github`.
- **GitHub App authentication is recommended.**  
  - `app_id`: The numeric App ID for your GitHub App.  
  - `installation_id`: The installation ID for the App on your repository/organization. If omitted, Mergebot will auto-discover it.  
  - `private_key`: the raw PEM string.  
  - You can also set these via environment variables: `GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`, `GITHUB_APP_PRIVATE_KEY`.
- `private_token`: (Legacy) Personal Access Token. If provided, Mergebot will use this instead of the App credentials.

### GitLab

```yaml
repository:
  type: gitlab
  gitlab:
    url: https://gitlab.example.com/api/v4
    private_token: YOUR_TOKEN # (not recommended, use env var)
    base_branch: main
```

- `type`: Must be `gitlab` (GitHub support coming soon)
- `gitlab`: Required if type is `gitlab`
- **Set the GitLab personal access token as the `GITLAB_PERSONAL_ACCESS_TOKEN` environment variable** (recommended).

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

## Full Example

```yaml
llm:
  model: gpt-4
  provider: openai

repository:
  type: gitlab
  gitlab:
    url: https://gitlab.example.com/api/v4
    base_branch: main

crews:
  CodeAnalysis:
    llm:
      model: gpt-4-turbo
      provider: openai
  ComplexityAnalysis:
    llm:
      model: anthropic.claude-3-opus-20240229
      provider: anthropic
  TestAnalysis:
    llm:
      model: gemini-pro
      provider: google

approval_policy:
  threshold: 3.0
  weights:
    CodeAnalysis: 0.4
    ComplexityAnalysis: 0.2
    TestAnalysis: 0.2
    RiskAnalysis: 0.2
```

---

> **Tip:** All fields are validated. If you provide an invalid agent name or omit a required field, Mergebot will fail fast with a clear error.
> For LLM API keys, always use environment variables for security.
