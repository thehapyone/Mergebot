# Mergebot Approval Policy Guide

This guide explains how to configure, tune, and understand the approval policy system in Mergebot.

---

## What is the Approval Policy?

The approval policy lets you control when Mergebot will auto-approve and merge a merge request (MR) based on the scores from its review agents.  
You can:
- Assign weights to each agent (e.g., CodeAnalysis, ComplexityAnalysis, TestAnalysis, RiskAnalysis)
- Set a threshold for auto-approval
- Make the approval process transparent and tunable for your team

---

## How the Approval Policy Works

### 1. Each Agent Produces a Score (0–10)
- Each agent outputs a score between 0 (no impact) and 10 (high impact/risk).

### 2. Weights Represent Importance
- The weights in the approval policy determine how much each agent’s score contributes to the overall impact score.
- Higher weight = more influence.

### 3. Weighted Impact Score Calculation

```
weighted_score = (score1 * weight1) + (score2 * weight2) + ... + (scoreN * weightN)
```

### 4. Threshold Determines Approval

- If `weighted_score <= threshold`, the MR is auto-approved.
- If `weighted_score > threshold`, the MR requires human review.

---

## Example Calculation

Suppose you have:
- CodeAnalysis: 2.0 (weight 0.5)
- ComplexityAnalysis: 4.0 (weight 0.2)
- TestAnalysis: 1.0 (weight 0.2)
- RiskAnalysis: 3.0 (weight 0.1)

Weighted score:
```
(2.0 * 0.5) + (4.0 * 0.2) + (1.0 * 0.2) + (3.0 * 0.1)
= 1.0 + 0.8 + 0.2 + 0.3
= 2.3
```
If the threshold is 3.0, this MR would be **auto-approved**.

---

## Valid Agent Names

When defining weights, you must use the exact agent names as defined in the system:

- `CodeAnalysis`
- `ComplexityAnalysis`
- `TestAnalysis`
- `RiskAnalysis`

---

## Realistic Example Weights

### Balanced Policy
```yaml
approval_policy:
  threshold: 3.0
  weights:
    CodeAnalysis: 0.4
    ComplexityAnalysis: 0.2
    TestAnalysis: 0.2
    RiskAnalysis: 0.2
```
- Use this if you want all review dimensions to have a similar influence.

### Code Quality Focus
```yaml
approval_policy:
  threshold: 3.0
  weights:
    CodeAnalysis: 0.5
    ComplexityAnalysis: 0.2
    TestAnalysis: 0.2
    RiskAnalysis: 0.1
```
- Use this if code correctness and standards are your top priority.

### Security/Risk-Averse
```yaml
approval_policy:
  threshold: 2.5
  weights:
    CodeAnalysis: 0.3
    ComplexityAnalysis: 0.1
    TestAnalysis: 0.2
    RiskAnalysis: 0.4
```
- Use this if you want to be conservative about risk, security, or compliance.

### Test-Driven
```yaml
approval_policy:
  threshold: 4.0
  weights:
    CodeAnalysis: 0.3
    ComplexityAnalysis: 0.1
    TestAnalysis: 0.5
    RiskAnalysis: 0.1
```
- Use this if you want to enforce strong test coverage as the main gate.

### Legacy Codebase (High Complexity Tolerance)
```yaml
approval_policy:
  threshold: 4.0
  weights:
    CodeAnalysis: 0.3
    ComplexityAnalysis: 0.1
    TestAnalysis: 0.3
    RiskAnalysis: 0.3
```
- Use this if you expect high complexity but want to balance risk and test coverage.

---

## Best Practices

- Weights should sum to 1.0 (or will be normalized).
- Use the agent names exactly as defined: `CodeAnalysis`, `ComplexityAnalysis`, `TestAnalysis`, `RiskAnalysis`.
- Tune the weights and threshold to match your team’s priorities and risk tolerance.
- Review and adjust after running Mergebot for a while.

---
 
## Relationship to Auto‑Merge

If merge auto-merge is enabled in your config, the merge decision uses a threshold that falls back to the approval policy threshold when not explicitly set:

- merge.threshold: If provided, the weighted score must be <= this value to merge.
- Fallback: If merge.threshold is null or omitted, Mergebot uses approval_policy.threshold for merge gating.

Notes:
- Draft/WIP pull/merge requests are never merged (hard rule).
- In addition to thresholds, merge rules (e.g., CI passed, no changes requested, mergeable, approval state) must also be satisfied. See merge configuration for details.

## Troubleshooting & FAQ

**Q: What happens if I use the wrong agent name or miss a weight?**  
A: Mergebot will fail fast with a clear error message. You must use all and only the valid agent names.

**Q: How do I make the policy stricter or more lenient?**  
A: Lower the threshold for stricter auto-approval, raise it for more leniency. Increase the weight of the most important agent(s).

**Q: What if I want to ignore an agent?**  
A: Set its weight to a very low value (but not zero, as all agents must be present).

---

## How to Use

- The approval policy is injected into the impact evaluator at runtime and used to guide the auto-approval decision.
- If the policy is not enabled or not present, Mergebot falls back to its default approval logic.

---

For more, see the main [Home](../index.md).
