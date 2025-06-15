# Mergebot

**Mergebot is an AI-powered code review and merge automation tool.**  
It leverages a system of intelligent "crews" (AI agents) to analyze, assess, and automate the review of Merge Requests (MRs) or Pull Requests (PRs) in your codebase.

Mergebot's unique value is its ability to act as an always-on, AI reviewer—performing deep impact assessments, code analysis, and risk evaluation.  
It can automatically approve and merge low-risk MRs, or escalate complex changes for human review, letting developers ship code faster while ensuring every change is reviewed for compliance and quality.

---

## How It Works: AI Crews, Impact Assessment, and Approval Policy

- **AI Crews/Agents**: Each crew (e.g., Code Analysis, Complexity, Risk, Test, Impact Evaluation) is an AI agent specialized for a review task. Crews are defined in modular Python classes and orchestrated in a flow.
- **Automated Review Flow**: When an MR is submitted, Mergebot's flow triggers each crew in sequence:
  1. **MR Details Extraction**: Gathers context and metadata.
  2. **Code Analysis Crew**: Reviews code changes for quality and standards.
  3. **Complexity Crew**: Assesses the complexity and maintainability of the changes.
  4. **Test Analysis Crew**: Checks for test coverage and quality.
  5. **Risk Analysis Crew**: Evaluates potential risks introduced by the MR.
  6. **Impact Evaluator**: Aggregates all assessments, applies the approval policy (if configured), and determines the overall impact and recommendation.
  7. **Publication Crew**: Decides whether to approve/merge the MR or escalate for human review.
- **Outcome**: Low-risk, compliant MRs are merged automatically (if they meet the approval policy). High-impact or risky changes are flagged for human attention.

---

## Features

- **AI-Driven Code Review**: Modular AI crews/agents perform deep, multi-dimensional analysis of every MR.
- **Automated Impact Assessment & Approval Policy**: MRs are automatically approved, merged, or escalated based on AI review and a configurable approval policy.
- **Configurable Workflows**: Define merge criteria, code analysis, risk assessment, and more via a single YAML config.
- **Modern, Centralized Logging**: All modules use a visually appealing, colorized logging system powered by [Rich](https://github.com/Textualize/rich).
- **Unified Configuration Validation**: All configuration is loaded and validated through a single, robust system.
- **Flexible Operation Modes**: Run as a webhook server or in ondemand mode, with clear subcommands for each.
- **Extensible Architecture**: Easily add new analysis "crews" or extend platform support.

---

## Configuration

> **Note:** The GitLab project/repository is now always provided via the required `--project` CLI flag.  

All configuration is managed via `mergebot/config.yaml` and validated by `mergebot/validator/config.py`.  
Key fields include repository type, platform credentials, crew settings, and (optionally) the approval policy.

Example:
```yaml
repository:
  type: gitlab
  gitlab:
    url: https://gitlab.example.com/api/v4
    private_token: YOUR_TOKEN
    base_branch: main
llm:
  model: gpt-4
crews:
  CodeAnalysis:
    llm:
      model: gpt-4

# Optional approval policy for auto-approval logic
approval_policy:
  enabled: true
  threshold: 3.0
  weights:
    CodeAnalysis: 0.5
    ComplexityAnalysis: 0.2
    TestAnalysis: 0.2
    RiskAnalysis: 0.1
```

---

## Usage

> **Note:** The `--project` flag is required for all running modes (`ondemand`, `webhook`).  
> The project/repository must always be specified on the command line.


## Approval Policy

:book: **For a full, scenario-driven guide, worked examples, and best practices, see [APPROVAL_POLICY.md](./docs/APPROVAL_POLICY.md).**

Mergebot supports an optional **approval policy** system that allows you to configure the criteria for auto-approving merge requests based on agent scores.

- The approval policy lets you specify a weighted scoring system for the impact evaluator.
- You can define a threshold and assign weights to each agent.
- If the weighted impact score is less than or equal to the threshold, the MR is auto-approved; otherwise, it requires human review.
- If no approval_policy is defined, Mergebot uses its default logic.

---

## Usage

<!-- CLI Mode removed: Mergebot no longer supports direct CLI mode for single MR processing. -->

### Ondemand Mode

Run a one-shot or periodic dashboard scan for a project:

```bash
mergebot ondemand --project mygroup/myrepo
# Or
python3 -m mergebot.app ondemand --project mygroup/myrepo
```

### Webhook Mode

Run as a webhook server to process MRs automatically for a project:

```bash
mergebot webhook --project mygroup/myrepo --port 8000
# Or
python3 -m mergebot.app webhook --project mygroup/myrepo --port 8000
```

---

## Running with Docker

You can run Mergebot in `ondemand` or `webhook` mode using Docker. The `--project` flag is always required:

```bash
# Ondemand mode
docker run --rm thehapyone/mergebot:test-latest ondemand --project mygroup/myrepo

# Webhook mode (exposes port 8000)
docker run --rm -p 8000:8000 thehapyone/mergebot:test-latest webhook --project mygroup/myrepo --port 8000
```

You can mount your own config file or data as needed:
```bash
docker run --rm -v $(pwd)/mergebot/config.yaml:/home/appuser/mergebot/config.yaml thehapyone/mergebot:test-latest ondemand --project mygroup/myrepo
```

---

## Docker Compose

A `docker-compose.yml` is provided for easy orchestration. The `--project` flag is always required in all commands.

**Ondemand mode:**
```bash
docker compose run mergebot ondemand --project mygroup/myrepo
```

**Webhook mode (exposes port 8000):**
```bash
docker compose run --service-ports mergebot webhook --project mygroup/myrepo --port 8000
```

**Custom configuration:**
Uncomment and edit the `volumes` section in `docker-compose.yml` to mount your own config or data.

---

## CI/CD & Docker Hub

On every merge to `master` or when a new tag is pushed, the GitHub Actions workflow will automatically build and push the Mergebot Docker image to [Docker Hub](https://hub.docker.com/r/thehapyone/mergebot).

- **Image Tags:**
  - On `master` merges: `latest`
  - On tag pushes: the tag name (e.g., `v1.2.3`)

- **Required GitHub Secrets:**
  - `DOCKERHUB_USERNAME`: Your Docker Hub username
  - `DOCKERHUB_TOKEN`: Your Docker Hub access token (create in Docker Hub > Account Settings > Security)

- **How it works:**
  1. The workflow logs in to Docker Hub using the provided secrets.
  2. Builds the Docker image.
  3. Pushes the image to Docker Hub with the appropriate tag.

- **Example image reference:**
  ```
  thehapyone/mergebot:latest
  thehapyone/mergebot:v1.2.3
  ```

You can then pull and run the image from Docker Hub in your environments:

```bash
docker pull thehapyone/mergebot:latest
docker run --rm thehapyone/mergebot:latest cli --mr-url ...
```

---

## Logging

Mergebot uses a centralized, visually appealing logging system based on [RichHandler](https://rich.readthedocs.io/en/stable/logging.html):

- All logs are colorized and structured for easy reading.
- Logging is consistent across all modules.
- Errors and tracebacks are clearly highlighted.

---

## Development & Contribution

- All configuration and platform logic is centralized for maintainability.
- Webhook and ondemand logic are cleanly separated in `app.py`.
- Utility functions (e.g., `get_platform_type`) are available in `mergebot/utils.py`.
- Contributions are welcome! Please open issues or pull requests.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
