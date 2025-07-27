# Installation

How to install and set up Mergebot.

## Requirements

- Python 3.12+ (if running from source)
- Docker (containerized usage)
- GitHub or GitLab account and project access


## Install via Docker

```bash
docker pull thehapyone/mergebot:latest
```

## Clone from Source

```bash
git clone https://github.com/thehapyone/Mergebot.git
cd Mergebot

poetry install

## Run the app
mergebot ondemand  --project=path_to_your_github_or_gitlab_project
```

---

> **Note:** Mergebot fully supports both GitHub and GitLab projects.
>
> For quick setup, see [Quickstart](quickstart.md).
