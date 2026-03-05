# Impact Evaluator Crew

The Impact Evaluator crew aggregates assessment results and applies the approval policy to determine the overall recommendation.

## Responsibilities

- Combine scores from code, complexity, test, and risk assessments.
- Apply the configured approval policy (thresholds, weights).
- Generate a final recommendation: auto-approve or escalate for human review.

## Implementation

- Uses an AI agent configured via `agents.yaml` and `tasks.yaml`.
- Runs after all other assessment crews in the flow pipeline.

> **See also:** [Flow Engine](../flow.md)
