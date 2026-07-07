# Docker Usage

Run Mergebot in a containerized environment using Docker.

## Pull the Image

```bash
docker pull thehapyone/mergebot:latest
```

## Workspace Volume

Each review clones the PR/MR into a temporary workspace under
`MERGEBOT_WORKSPACE_DIR` (image default: `/var/lib/mergebot/workspaces`). Mount a
**disk-backed, writable** volume there — never a tmpfs/ramfs mount — sized for the
configured fan-out (`workers x max-concurrency x context.workspace.max_repo_mb`).
Workspaces are removed after every review and an orphan sweeper cleans up after
crashes; if the volume is missing or full, reviews degrade to diff-only instead of
failing.

```bash
docker volume create mergebot-workspaces
```

## Run in Ondemand Mode

```bash
docker run --rm \
  -v $(pwd)/config-gitlab.yaml:/config/config.yaml \
  -v mergebot-workspaces:/var/lib/mergebot/workspaces \
  -e CONFIG_PATH=/config/config.yaml \
  thehapyone/mergebot:latest ondemand --max-concurrency 4
```

## Run in Webhook Mode

```bash
docker run --rm -p 8000:8000 \
  -v $(pwd)/config-gitlab.yaml:/config/config.yaml \
  -e CONFIG_PATH=/config/config.yaml \
  thehapyone/mergebot:latest webhook --port 8000 --max-concurrency 2
```

> Configure `GITLAB_WEBHOOK_SECRET` or `GITHUB_WEBHOOK_SECRET` (e.g. `-e GITLAB_WEBHOOK_SECRET=...`) when running in webhook mode so incoming events are authenticated.
> Projects are discovered from `repository.projects`; adjust `--max-concurrency` to limit parallel analyses.
> Sample configuration files are provided in the repo (`example-config-gitlab.yaml`, `example-config-github.yaml`).

## Mount Custom Config

```bash
docker run --rm \
  -v $(pwd)/mergebot/config.yaml:/home/appuser/mergebot/config.yaml \
  thehapyone/mergebot:latest ondemand --max-concurrency 2 --interval 900
```

> Adjust `--interval` to control how frequently ondemand scans repeat; omit it for a single pass.

> **Tip:** For Docker Compose instructions, see [Docker Compose](docker_compose.md).
