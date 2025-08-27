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
      # GitHub App (recommended for GitHub)
      # - GITHUB_APP_ID=${GITHUB_APP_ID}
      # - GITHUB_APP_PRIVATE_KEY=${GITHUB_APP_PRIVATE_KEY}
      # GitLab PAT (for GitLab)
      - GITLAB_PERSONAL_ACCESS_TOKEN=${GITLAB_PERSONAL_ACCESS_TOKEN}
```

## Usage

```bash
docker compose run mergebot
```

> **Tip:** You can schedule this job in a CI/CD pipeline for regular analysis.
