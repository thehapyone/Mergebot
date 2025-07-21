# Configuration Schema

This page documents the fields and structure of the Mergebot configuration file (`.mergebot.yml` and `mergebot/config.yaml`).

## Top-Level Fields

| Field           | Type     | Description                                      |
|-----------------|----------|--------------------------------------------------|
| llm             | object   | Global LLM configuration (provider, model)       |
| repository      | object   | Repository configuration (type, gitlab, etc.)    |
| crews           | object   | Per-crew configuration (optional)                |
| approval_policy | object   | Approval policy configuration (optional)         |
| analysis        | object   | Analysis options (optional, e.g. MR limits)      |

---

## Analysis Options

You can control how many merge requests (MRs) Mergebot will analyze at a time by setting the `analysis.max_mrs` field. If omitted or set to 0, there is no limit.

By default, Mergebot will **skip Draft or WIP MRs**. To analyze them, set `draft_mrs: true`.

```yaml
analysis:
  max_mrs: 10  # Maximum number of MRs to analyze at once (0 or missing = unlimited)
  draft_mrs: false  # If true, analyze Draft/WIP MRs. If false (default), skip Draft/WIP MRs.
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

```yaml
repository:
  type: gitlab
  gitlab:
    url: https://gitlab.example.com/api/v4
    private_token: YOUR_TOKEN  # (not recommended, use env var)
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
