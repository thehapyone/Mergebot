# Mergebot

[![View Docs](https://img.shields.io/badge/docs-online-blue?logo=githubpages&style=flat-square)](https://thehapyone.github.io/Mergebot/)

**Automated impact assessment and code review for GitHub & GitLab.**

- Automated, multi-agent code review
- Impact assessment and approval policy
- Dashboard and ondemand runners
- Extensible, modular architecture
- Supports both GitHub and GitLab workflows

---

## Why Mergebot?

Mergebot is an **impact assessment and automation tool for change requests**. For every pull or merge request (PR/MR), Mergebot automatically calculates an impact score—classifying the change as low, medium, or high impact. Based on this impact evaluation, Mergebot can take intelligent actions:

- **Low-impact changes** (below a configurable threshold) can be auto-approved and merged, accelerating delivery without breaking compliance or review standards.
- **High-impact changes** trigger a requirement for human review, ensuring that risky or complex changes always get the attention they deserve.

This approach allows teams to automate the "low-hanging fruit"—routine, low-risk changes—while maintaining rigorous standards and compliance for everything else.

**Mergebot** is not just a code review bot—it's an automated impact assessor and compliance enforcer for your codebase.

---

> **Full documentation:**  
> 👉 [https://thehapyone.github.io/Mergebot/](https://thehapyone.github.io/Mergebot/)  
> (auto-published on every push to `main` via GitHub Actions)

---

## Quick Install

```bash
# Docker (recommended)
docker pull thehapyone/mergebot:latest
```

## Usage

See the [Quickstart guide](docs/quickstart.md) for setup and usage instructions.

---

> Mergebot fully supports **GitHub** and **GitLab** workflows.  
> Other VCS platforms may be supported in the future.
