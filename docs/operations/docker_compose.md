# Docker Compose

Run Mergebot using Docker Compose for easy orchestration.

## Example docker-compose.yml

```yaml
version: "3.8"
services:
  mergebot:
    image: thehapyone/mergebot:latest
    command: ondemand --project mygroup/myrepo
    volumes:
      - ./mergebot/config.yaml:/home/appuser/mergebot/config.yaml
    environment:
      - GITLAB_TOKEN=${GITLAB_TOKEN}
```

## Usage

```bash
docker compose run mergebot
```

> **Tip:** You can schedule this job in a CI/CD pipeline for regular analysis.
