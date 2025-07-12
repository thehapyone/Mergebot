# Flow Engine

The Flow Engine orchestrates the Mergebot review pipeline using CrewAI.

## Overview

- Defines the sequence of crews (agents) and their dependencies.
- Manages state and parallel execution of assessments.
- Aggregates results and applies the approval policy.

## Execution Sequence

1. **MR Details Extraction**: Gather context and metadata.
2. **Code Analysis, Complexity, Test, Risk**: Run in parallel.
3. **Impact Evaluation**: Aggregate scores and recommendations.
4. **Publication**: Approve/merge or escalate for human review.

## Extensibility

- Add new crews by extending the flow and wiring new listeners.
- Approval policy can be customized via configuration.

> **See also:** [Architecture Overview](overview.md), [Crews](crews/code_analysis.md)
