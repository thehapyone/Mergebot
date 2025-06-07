# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VERSION=2.1.2
ENV REQUESTS_CA_BUNDLE="/etc/ssl/certs/ca-certificates.crt"

# Create a non-root user
RUN adduser --disabled-password --gecos '' appuser

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

# Configure Poetry to use in-project virtualenvs and install dependencies (no-root)
RUN poetry config virtualenvs.in-project true && \
    poetry install --no-cache --no-plugins --no-interaction --no-ansi --no-root

# Copy the rest of the application's code
COPY mergebot ./mergebot

# Install the current project (fast, only project code, not dependencies)
RUN poetry install --no-cache --no-plugins --no-interaction --no-ansi

# Use the CLI as the entrypoint
ENTRYPOINT ["mergebot"]
