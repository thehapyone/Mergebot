# Docker Usage

Run Mergebot in a containerized environment using Docker.

## Pull the Image

```bash
docker pull thehapyone/mergebot:latest
```

## Run in Ondemand Mode

```bash
docker run --rm thehapyone/mergebot:latest ondemand --project mygroup/myrepo
```

## Run in Webhook Mode

```bash
docker run --rm -p 8000:8000 thehapyone/mergebot:latest webhook --project mygroup/myrepo --port 8000
```

## Mount Custom Config

```bash
docker run --rm -v $(pwd)/mergebot/config.yaml:/home/appuser/mergebot/config.yaml thehapyone/mergebot:latest ondemand --project mygroup/myrepo
```

> **Tip:** For Docker Compose instructions, see [Docker Compose](docker_compose.md).
