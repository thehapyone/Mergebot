.PHONY: all format lint spell_check spell_fix build deploy help

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
	@echo 'format        - run code formatters'
	@echo 'lint          - run linters'
	@echo 'spell_check   - run codespell for spelling errors'
	@echo 'spell_fix     - auto-fix spelling errors with codespell'
	@echo 'build         - build the Docker image'
	@echo 'deploy        - push the Docker image to Docker Hub'
	@echo 'help          - show this help message'
