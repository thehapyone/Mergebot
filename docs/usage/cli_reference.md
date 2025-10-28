# CLI Reference

Mergebot provides a command-line interface for running code review and merge automation tasks.

## Usage

```bash
mergebot --help
```

## Commands

- `ondemand` — Run a one-shot analysis of all open merge requests in a project.
- `webhook` — Run as a webhook server to process PR/MR events automatically (requires a configured webhook secret). Reads all repositories from `repository.projects`.

## Options

| Option         | Description                        |
| -------------- | ---------------------------------- |
| --workers          | Number of parallel workers (ondemand) |
| --port             | Port for webhook server             |
| --max-concurrency  | Max number of projects to process concurrently |
| --interval         | Interval (seconds) between ondemand scans |
| --help             | Show help message                   |

> **Security:** Set `GITLAB_WEBHOOK_SECRET` or `GITHUB_WEBHOOK_SECRET` (or the corresponding config field) before running in webhook mode to authenticate incoming events.
> **Note:** Both webhook and ondemand modes automatically fan out across `repository.projects`; adjust `--max-concurrency` to throttle workload.

> Only ondemand mode accepts `--interval`; omit it to perform a single pass across all projects.

> **Tip:** For most users, the recommended mode is `ondemand` via CI/CD.

---

## Tools

### GetPipelineDetails

Fetch detailed information about a specific pipeline (GitHub Actions run or GitLab pipeline) including job status, times, web links, and error counts. Output is unified for both GitHub and GitLab.

**Usage Example (pseudo-API or tool invocation):**
```python
# Example API usage
result = GetPipelineDetailsTool()._run(pipeline_id="7419423339")
print(result)
```

**Input:**
- `pipeline_id`: The run_id (GitHub) or pipeline_id (GitLab).

**Output:**
- Human-readable summary with:
  - Pipeline/Run metadata (status, conclusion, ref, commit sha, URL)
  - List of jobs (with error/warning counts, status, HTML URLs)
  - Totals for errors/warnings

**When to Use:**
- Inspect a failed/successful CI run/job in rich detail
- Debug PR/MR workflows

**See also:** Pipeline summaries are automatically appended to PR details as part of normal analysis.

---

See [Running Mergebot](running.md) for all supported CLI, CI, and integration patterns.
