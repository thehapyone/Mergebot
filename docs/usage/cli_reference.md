# CLI Reference

Mergebot provides a command-line interface for running code review and merge automation tasks.

## Usage

```bash
mergebot --help
```

## Commands

- `ondemand` — Run a one-shot analysis of all open merge requests in a project.
- `webhook` — (Experimental) Run as a webhook server to process MRs automatically.  
  *Note: Webhook mode is not actively maintained and may be removed in future releases.*

## Options

<!-- TODO: Autogenerate this section from the CLI help output. -->

| Option         | Description                        |
| -------------- | ---------------------------------- |
| --project      | GitLab project/repo path (required) |
| --workers      | Number of parallel workers          |
| --port         | Port for webhook server             |
| --help         | Show help message                   |

> **Tip:** For most users, the recommended mode is `ondemand` via CI/CD.
