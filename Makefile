.PHONY: all format lint test tests

# Default target executed when no arguments are given to make.
all: help

######################
# LINTING AND FORMATTING
######################

# Define a variable for Python and notebook files.
PYTHON_FILES=.
MYPY_CACHE=.mypy_cache
lint format: PYTHON_FILES=.
lint_tests: PYTHON_FILES=tests
lint_tests: MYPY_CACHE=.mypy_cache_test

lint lint_tests:
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
	@echo 'format                       - run code formatters'
	@echo 'lint                         - run linters'
