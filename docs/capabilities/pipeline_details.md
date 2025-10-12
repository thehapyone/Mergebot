# Cross-Platform Pipeline/CI Analysis

Mergebot provides unified analysis and visibility into CI pipelines for both GitHub Actions and GitLab CI, giving developers and reviewers a complete view of workflow/job status directly in every PR/MR.

## What It Does

- For each pull/merge request, Mergebot identifies and summarizes the most relevant workflow run or pipeline:
  - **GitHub**: Uses the latest relevant Actions workflow run for the PR's head commit or branch.
  - **GitLab**: Uses the linked pipeline for the merge request's head.

- Presents a human-readable summary including:
  - **Pipeline/Run Metadata**: ID, status, conclusion/result, branch/ref, SHA, timestamps, web link.
  - **Job Table**: Each job’s name, status, conclusion, run times, errors/warnings count, and direct job URL.
  - **Totals**: Number of jobs, error count, warning count (warnings currently GitLab-only).

- All output is harmonized so summary and fields are consistent across platforms.

## Where You See It

- **Pull/Merge Request Details**: Pipeline summary is appended to every PR/MR analysis comment or summary.
- **CLI & Tooling**: Use the `GetPipelineDetails` tool call to fetch pipeline/run details by ID for either provider.

## How the Matching Works

- **GitHub**:
  - Primary: finds workflow runs with matching `head_sha` to PR's HEAD commit.
  - Fallback: finds recent runs for `event=pull_request`, current branch, and checks if PR number matches in the run’s `pull_requests` array.
- **GitLab**: Uses merge request’s head pipeline directly.

- If no run/pipeline is found, the field is omitted.

## Permissions

- **GitHub App**: Requires `Actions: Read` permission to access workflow runs and jobs.
- **GitHub PAT**: Requires `repo` + `actions:read` scopes.
- **GitLab Token**: Usual API read token.

## Output Example

```
## Pipeline Information:
  Pipeline ID : 123456789
  Status      : completed
  Conclusion  : success
  Ref         : feature/unified-ci
  Head SHA    : cc8f...
  Created At  : 2025-09-20T14:05:18Z
  Updated At  : 2025-09-20T14:07:50Z
  Web URL     : https://github.com/org/repo/actions/runs/123456789
  Total Jobs      : 3
  Total Warnings  : 0
  Total Errors    : 1
  Jobs:
{
  "id": 98765,
  "name": "build",
  "status": "completed",
  "conclusion": "success",
  "started_at": "2025-09-20T14:05:30Z",
  "completed_at": "2025-09-20T14:06:15Z",
  "html_url": "https://github.com/org/repo/runs/98765",
  "errors_count": 0,
  "warnings_count": 0
}
{
  "id": 98766,
  "name": "test",
  "status": "completed",
  "conclusion": "failure",
  "started_at": "2025-09-20T14:06:18Z",
  "completed_at": "2025-09-20T14:07:40Z",
  "html_url": "https://github.com/org/repo/runs/98766",
  "errors_count": 1,
  "warnings_count": 0
}
...
```

## Troubleshooting & Notes

- **Forked PRs**: GitHub Actions runs/analysis always occur on the base repository.
- **No Pipeline Found**: If no CI run/job exists for a PR, the summary is omitted (not an error).
- **Warning Counts**: Warnings are currently available for GitLab where exposed in logs, but not for GitHub Actions jobs (future: may parse artifacts/logs).
- **API Fallback**: All GitHub job details use the REST endpoint due to current PyGithub limitations.
- **Security**: Never expose secrets/tokens via logs or summaries.
- **Error Handling**: If API errors occur, the summary notes the failure reason for transparency.

## Related Features

- See [CLI Reference](../usage/cli_reference.md) for tool usage.
- See [Merge & Approval Guardrails](./capabilities.md) for info on how CI/pipeline state affects auto-merge and approval flows.
