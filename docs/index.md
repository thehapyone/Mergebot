# Mergebot Documentation

Welcome to the official documentation for **Mergebot** – the AI-powered code review and merge automation tool.

---

## Why Mergebot?

The core idea behind Mergebot is **impact assessment for change requests**. For every pull or merge request (PR/MR), Mergebot automatically calculates an impact score—classifying the change as low, medium, or high impact. Based on this impact evaluation, Mergebot can take intelligent actions:

- **Low-impact changes** (below a configurable threshold) can be auto-approved and merged, accelerating delivery without breaking compliance or review standards.
- **High-impact changes** trigger a requirement for human review, ensuring that risky or complex changes always get the attention they deserve.

This approach allows teams to automate the "low-hanging fruit"—routine, low-risk changes—while maintaining rigorous standards and compliance for everything else. Mergebot is designed to help teams ship code faster, reduce manual review workload, and raise the bar for code quality and traceability.

**Mergebot** is not just a code review bot—it's an automated impact assessor and compliance enforcer for your codebase.

---

## Benefits

- **Accelerate Delivery:** Ship code faster by automating routine review tasks and approvals for low-risk changes.
- **Improve Code Quality:** Consistent, multi-dimensional analysis on every PR/MR—no more missed issues or "rubber-stamp" reviews.
- **Reduce Manual Effort:** Let Mergebot handle the heavy lifting, so your team can focus on high-value work.
- **Increase Transparency:** Every decision is logged, auditable, and explainable—ideal for compliance and regulated environments.
- **Scale with Confidence:** As your team and codebase grow, Mergebot ensures review standards never slip.
- **Onboard Faster:** New team members get instant, actionable feedback on their code, accelerating ramp-up.

---

## Use Cases

- **Scaling Code Review:** Large teams or organizations with many contributors can maintain high review standards without slowing down.
- **Compliance & Audit:** Regulated industries (finance, healthcare, etc.) can ensure every change is reviewed and logged for compliance.
- **Open Source Projects:** Automate triage and review for community contributions, reducing maintainer burnout.
- **Onboarding New Developers:** Provide consistent, actionable feedback to new team members, speeding up onboarding and reducing errors.
- **Legacy Code Modernization:** Systematically improve code quality and test coverage across large, aging codebases.

---

- **Automated, multi-agent code review**
- **Impact assessment and approval policy**
- **Dashboard and ondemand runners**
- **Extensible, modular architecture**
- **Supports both GitHub and GitLab workflows**

---

## How Mergebot Works

Mergebot automates the code review and merge process using a series of specialized AI "crews" that analyze every pull or merge request (PR/MR) for quality, risk, test coverage, and more. Here’s a high-level workflow:

```mermaid
flowchart TD
    A[Developer opens Pull or Merge Request (PR/MR)] --> B[Mergebot triggers pipeline]
    B --> C[Code Analysis Crew: Lint, Style, Complexity]
    C --> D[Test Analysis Crew: Coverage, Test Quality]
    D --> E[Risk & Impact Crew: Change Impact, Risk Assessment]
    E --> F[Approval Policy Crew: Enforce Rules]
    F --> G[Publication Crew: Merge or Request Changes]
    G --> H[Feedback posted to PR/MR]
    H --> I[PR/MR merged or sent back for revision]
```

- **Crews** are modular and can be extended or customized.
- Each crew focuses on a specific aspect of code review.
- All decisions and feedback are posted directly to the PR/MR for full transparency.

---

## Real-World Scenario: Mergebot in Action

**Scenario:**
A fintech company with a rapidly growing engineering team struggles to keep up with code reviews. Manual reviews are inconsistent, and compliance requirements demand every change be logged and justified.

**With Mergebot:**

- Developers open PRs/MRs as usual. Mergebot automatically analyzes each PR/MR using its AI crews.
- The Code Analysis Crew flags a potential security issue and suggests a fix.
- The Test Analysis Crew notes missing test coverage and recommends additional tests.
- The Approval Policy Crew enforces the company’s compliance rules, requiring a second review for high-risk changes.
- All feedback is posted directly to the PR/MR, with clear explanations and links to documentation.
- Once all guardrails pass (impact score ≤ threshold, CI/approvals satisfied), Mergebot merges the PR/MR and logs the decision for audit purposes.
- If a merge is blocked, Mergebot now posts a detailed comment outlining the score, thresholds, and guardrail reason so teams can fix issues quickly.

**Result:**
The team ships code faster, maintains high quality, and meets compliance requirements—without burning out reviewers.

---

> **Platform Support:**
> Mergebot fully supports **GitHub** and **GitLab** workflows.
> Other VCS platforms may be supported in the future.

Use the navigation to explore installation, configuration, usage, architecture, and more.

---

## Documentation Hosting

This documentation is **automatically published** to [GitHub Pages](https://thehapyone.github.io/Mergebot/) on every push to the `main` branch.

To preview changes locally before pushing:
```bash
poetry install
poetry run mkdocs serve
```

> **Note:** This documentation is a work in progress. See the [GitHub repository](https://github.com/thehapyone/Mergebot) for the latest updates.
