# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VERSION=2.2.1
ENV REQUESTS_CA_BUNDLE="/etc/ssl/certs/ca-certificates.crt"

# Install required packages for GitLab Runner compatibility, plus git + ripgrep for
# the per-review workspace and fact-pack context builder.
RUN apt-get update && apt-get install -y --no-install-recommends \
    coreutils \
    git \
    ripgrep \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN adduser --disabled-password --gecos '' appuser

# Per-review workspace root: must be a disk-backed, writable volume (never tmpfs),
# sized for the configured review fan-out (workers x max_concurrency x max_repo_mb).
ENV MERGEBOT_WORKSPACE_DIR=/var/lib/mergebot/workspaces

# Headless container: no CrewAI update-check panel (avoids a PyPI call per flow)
# and no tracing consent flows.
ENV CREWAI_DISABLE_VERSION_CHECK=true
ENV CREWAI_TRACING_ENABLED=false
RUN mkdir -p "$MERGEBOT_WORKSPACE_DIR" && chown -R appuser:appuser /var/lib/mergebot

# Set work directory
WORKDIR /home/appuser
ENV PYTHONPATH=/home/appuser
ENV PATH="/home/appuser/.venv/bin:$PATH"

# Install Poetry
RUN pip install --upgrade pip && \
    pip install "poetry==$POETRY_VERSION"

# Copy only the files needed for installing dependencies
COPY pyproject.toml poetry.lock README.md ./

USER appuser

# Configure Poetry to use in-project virtualenvs and install dependencies (no-root).
# Runtime dependencies include the code-review-graph CLI used by the fact-pack builder.
RUN poetry config virtualenvs.in-project true && \
    poetry install --no-cache --no-plugins --no-interaction --no-ansi --no-root

# Copy the rest of the application's code
COPY mergebot ./mergebot

# Install the current project (fast, only project code, not dependencies)
RUN poetry install --no-cache --no-plugins --no-interaction --no-ansi

# Use the CLI as the entrypoint
CMD ["mergebot"]
