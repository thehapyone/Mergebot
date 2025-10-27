# Docker Usage

Run Mergebot in a containerized environment using Docker.

## Pull the Image

```bash
docker pull thehapyone/mergebot:latest
```

## Run in Ondemand Mode

```bash
docker run --rm \
  -v $(pwd)/config-gitlab.yaml:/config/config.yaml \
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
