# Mergebot Onboarding Workflow & Configuration

## Overview

Mergebot uses a repository-based configuration file, `.mergebot.yml`, to control its behavior. This onboarding workflow ensures every repository is properly configured before Mergebot runs, providing a transparent, user-friendly, and auditable setup process.

---

## How the Onboarding Workflow Works

### 1. **Startup Check**

When Mergebot starts (in any mode), it performs the following steps:

- **Detects the platform** (e.g., GitLab, GitHub; currently GitLab is supported).
- **Checks for `.mergebot.yml`** in the default branch of the repository.

### 2. **If `.mergebot.yml` Exists and is Valid**

- The YAML is parsed and merged into the runtime/server config.
- The merged config is validated against the schema.
- If valid, Mergebot proceeds with its normal operation.

### 3. **If `.mergebot.yml` is Missing**

- Mergebot checks for an existing onboarding PR (from the `mergebot/onboarding` branch).
- **If an onboarding PR already exists:**  
  - Mergebot logs the PR URL and aborts startup.
  - The user must merge the PR to enable Mergebot.
- **If no onboarding PR exists:**  
  - Mergebot creates a new onboarding PR with a default `.mergebot.yml`.
  - The user must review, customize, and merge the PR to enable Mergebot.

### 4. **If `.mergebot.yml` is Present but Invalid**

- If the YAML is malformed or does not conform to the schema:
  - Mergebot logs a clear error and aborts startup.
  - The user must fix the YAML syntax or config errors in the repo.

---

## Configuration Precedence

1. **Server/Default Config** (e.g., `config.yaml`)
2. **Repo Config** (`.mergebot.yml` in the default branch)  
   - Repo config takes precedence and can override server defaults.

---

## Onboarding PR Details

- The onboarding PR is created from the `mergebot/onboarding` branch to the default branch.
- Only one onboarding PR is ever open at a time (Mergebot checks for duplicates before creating).
- The PR contains a default `.mergebot.yml` and instructions for customization.
- Once merged, Mergebot will use the repo config for all future operations.

---

## Error Handling

- **Missing config:** Onboarding PR is created (or referenced if already open).
- **Invalid YAML:** Startup aborts with a clear error; user must fix the file.
- **Unsupported platform:** Startup aborts with an error.

---

## Platform Agnostic Design

- The onboarding workflow is designed to support multiple platforms.
- Currently, only GitLab is implemented; GitHub and others can be added with minimal changes.

---

## Example: Default `.mergebot.yml`

```yaml
# Default Mergebot configuration
# See https://github.com/your-org/mergebot for documentation
repository:
  type: "gitlab"
  gitlab:
    base_branch: "main"

approval_policy:
  enabled: true
  threshold: 3.0
  weights:
    CodeAnalysis: 0.4
    ComplexityAnalysis: 0.2
    TestAnalysis: 0.2
    RiskAnalysis: 0.2
```

---

## Summary

- Mergebot will not run unless a valid `.mergebot.yml` is present in the repo.
- The onboarding PR workflow ensures every repo is properly configured, with no duplicates.
- All config is validated and merged in a robust, platform-agnostic way.

For more details, see the main [README.md](../README.md) or [APPROVAL_POLICY.md](APPROVAL_POLICY.md).
