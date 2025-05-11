# Mergebot

**Mergebot is an AI-powered code review and merge automation tool.**  
It leverages a system of intelligent "crews" (AI agents) to analyze, assess, and automate the review of Merge Requests (MRs) or Pull Requests (PRs) in your codebase.

Mergebot's unique value is its ability to act as an always-on, AI reviewer—performing deep impact assessments, code analysis, and risk evaluation.  
It can automatically approve and merge low-risk MRs, or escalate complex changes for human review, letting developers ship code faster while ensuring every change is reviewed for compliance and quality.

---

## How It Works: AI Crews & Automated Impact Assessment

- **AI Crews/Agents**: Each crew (e.g., Code Analysis, Complexity, Risk, Test, Impact Evaluation) is an AI agent specialized for a review task. Crews are defined in modular Python classes and orchestrated in a flow.
- **Automated Review Flow**: When an MR is submitted, Mergebot's flow triggers each crew in sequence:
  1. **MR Details Extraction**: Gathers context and metadata.
  2. **Code Analysis Crew**: Reviews code changes for quality and standards.
  3. **Complexity Crew**: Assesses the complexity and maintainability of the changes.
  4. **Test Analysis Crew**: Checks for test coverage and quality.
  5. **Risk Analysis Crew**: Evaluates potential risks introduced by the MR.
  6. **Impact Evaluator**: Aggregates all assessments to determine the overall impact.
  7. **Publication Crew**: Decides whether to approve/merge the MR or escalate for human review.
- **Outcome**: Low-risk, compliant MRs are merged automatically. High-impact or risky changes are flagged for human attention.

**This means developers can focus on shipping features, not on the noise of continuous MRs—while always having an AI reviewer to ensure code quality and compliance.**

---

## Features

- **AI-Driven Code Review**: Modular AI crews/agents perform deep, multi-dimensional analysis of every MR.
- **Automated Impact Assessment**: MRs are automatically approved, merged, or escalated based on AI review.
- **Configurable Workflows**: Define merge criteria, code analysis, risk assessment, and more via a single YAML config.
- **Modern, Centralized Logging**: All modules use a visually appealing, colorized logging system powered by [Rich](https://github.com/Textualize/rich).
- **Unified Configuration Validation**: All configuration is loaded and validated through a single, robust system.
- **Flexible CLI & Webhook Modes**: Run as a CLI tool or as a webhook server, with clear subcommands for each.
- **Extensible Architecture**: Easily add new analysis "crews" or extend platform support.

---

## Configuration

All configuration is managed via `mergebot/config.yaml` and validated by `mergebot/validator/config.py`.  
Key fields include repository type, platform credentials, and crew settings.

Example:
```yaml
repository:
  type: gitlab
  gitlab:
    url: https://gitlab.example.com/api/v4
    private_token: YOUR_TOKEN
    project: your/project
    base_branch: main
llm:
  model: gpt-4
crews:
  code_analysis:
    llm:
      model: gpt-4
```

---

## Usage

### CLI Mode

Process a Merge Request directly from the command line:

```bash
python3 -m mergebot.app cli --mr-url "https://gitlab.example.com/your/project/-/merge_requests/123"
```

### Webhook Mode

Run as a webhook server to process MRs automatically:

```bash
python3 -m mergebot.app webhook --port 8000
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
- CLI and webhook logic are cleanly separated in `app.py`.
- Utility functions (e.g., `get_platform_type`) are available in `mergebot/utils.py`.
- Contributions are welcome! Please open issues or pull requests.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
