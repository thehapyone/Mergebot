.PHONY: all format lint spell_check spell_fix test pre-commit-install pre-commit-run build deploy help

# Default target executed when no arguments are given to make.
all: help

######################
# LINTING AND FORMATTING
######################

PYTHON_FILES=.

lint:
	poetry run ruff check $(PYTHON_FILES)

format:
	poetry run ruff format $(PYTHON_FILES)
	poetry run ruff check --select I --fix $(PYTHON_FILES)

spell_check:
	poetry run codespell --toml pyproject.toml

spell_fix:
	poetry run codespell --toml pyproject.toml -w

######################
# TESTING
######################

test:
	poetry run pytest tests/

pre-commit-install:
	poetry run pre-commit install

pre-commit-run:
	poetry run pre-commit run --all-files

######################
# BUILDING AND PUBLISHING
######################

TAG?=latest
build:
	docker build -t thehapyone/mergebot:$(TAG) .

deploy:
	docker push thehapyone/mergebot:$(TAG)

######################
# HELP
######################

help:
	@echo '----'
	@echo 'format             - run code formatters'
	@echo 'lint               - run linters'
	@echo 'spell_check        - run codespell for spelling errors'
	@echo 'spell_fix          - auto-fix spelling errors with codespell'
	@echo 'test               - run the pytest suite'
	@echo 'pre-commit-install - install pre-commit hooks'
	@echo 'pre-commit-run     - run pre-commit on all files'
	@echo 'build              - build the Docker image'
	@echo 'deploy             - push the Docker image to Docker Hub'
	@echo 'help               - show this help message'
