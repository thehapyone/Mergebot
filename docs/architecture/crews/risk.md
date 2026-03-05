# Risk Analysis Crew

The Risk Analysis crew evaluates potential risks introduced by code changes.

## Responsibilities

- Assess the likelihood and impact of introducing bugs or regressions.
- Identify risky patterns or dependencies.
- Contribute to the overall impact score for merge requests.

## Implementation

- Uses an AI agent configured via `agents.yaml` and `tasks.yaml`.
- Runs as part of the main flow pipeline.

> **See also:** [Flow Engine](../flow.md)
