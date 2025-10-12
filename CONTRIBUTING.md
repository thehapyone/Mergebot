# Contributing to Mergebot

Thank you for your interest in contributing to Mergebot! This guide will help you get started.

## Development Setup

### Prerequisites
- Python 3.12
- Poetry 2.1.2+
- Git

### Initial Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/thehapyone/Mergebot.git
   cd Mergebot
   ```

2. **Install dependencies**
   ```bash
   poetry install --with dev
   ```

3. **Install pre-commit hooks** (strongly recommended)
   ```bash
   make pre-commit-install
   ```

   This will automatically run code quality checks before each commit.

## Code Quality Standards

Mergebot follows strict Python code quality standards to ensure maintainability and consistency.

### Automated Tools

We use the following tools to enforce code quality:

- **Ruff** - Fast Python linter and formatter
- **Codespell** - Spelling checker
- **Pre-commit** - Git hooks for automated checks

### Running Checks Locally

Before submitting a PR, ensure your code passes all checks:

```bash
# Format code
make format

# Run linting
make lint

# Check spelling
make spell_check

# Run all pre-commit checks
make pre-commit-run
```

### Code Style Guidelines

1. **Naming Conventions (PEP 8)**
   - `snake_case` for functions, variables, and methods
   - `PascalCase` for classes
   - `UPPER_CASE` for true module-level constants only
   - Class attributes should use `lowercase_with_underscores`, not `CAPITALS`

   ```python
   # Good
   class GitHubAPIWrapper:
       request_timeout = (5, 30)  # class attribute

   # Bad
   class GitHubAPIWrapper:
       REQUEST_TIMEOUT = (5, 30)  # looks like a constant but isn't
   ```

2. **Request Timeouts**
   - Always add timeouts to `requests.get()` and `requests.post()` calls
   ```python
   resp = requests.get(url, headers=headers, timeout=self.request_timeout)
   ```

3. **Error Handling**
   - Use try-except blocks for network calls
   - Log warnings/errors appropriately
   ```python
   try:
       resp = requests.get(url, timeout=timeout)
   except Exception as e:
       logger.warning(f"Failed to fetch: {e}")
   ```

4. **Pagination**
   - Always handle pagination for API calls that could return large datasets
   - Use configurable page sizes

5. **Magic Numbers**
   - Extract hardcoded values to named constants
   ```python
   # Good
   log_tail_lines = 30
   snippet[-log_tail_lines:]

   # Bad
   snippet[-30:]
   ```

### Pre-commit Hooks

Pre-commit hooks automatically run on every commit. They will:
- Format your code with Ruff
- Check for common issues
- Verify YAML/TOML syntax
- Check for large files
- Fix trailing whitespace

If a check fails, the commit is blocked. Fix the issues and try again.

## CI/CD Pipeline

Every pull request automatically runs:
1. **Linting** - Ruff checks for code quality issues
2. **Formatting** - Ensures consistent code style
3. **Spell checking** - Catches typos in code and docs
4. **Docker build** - Verifies the image builds correctly

PRs must pass all checks before merging.

## Development Workflow

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write clean, well-documented code
   - Follow the code style guidelines above
   - Add tests if applicable

3. **Run checks locally**
   ```bash
   make format
   make lint
   make spell_check
   ```

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: your descriptive commit message"
   ```

   Pre-commit hooks will run automatically.

5. **Push and create a PR**
   ```bash
   git push origin feature/your-feature-name
   ```

## Ruff Configuration

Our Ruff configuration (in `pyproject.toml`) enforces:
- **PEP 8** naming conventions (rule `N`)
- **Modern Python idioms** (rule `UP`)
- **Bug detection** (rule `B`)
- **Code simplification** (rule `SIM`)
- **Pylint rules** (rule `PL`)

These rules catch common issues like:
- Non-Pythonic naming (e.g., `REQUEST_TIMEOUT` for class attributes)
- Missing error handling
- Unused imports
- Code complexity issues

## Questions?

- Check the [documentation](https://docs.mergebot.dev)
- Open a [GitHub discussion](https://github.com/thehapyone/Mergebot/discussions)
- Report bugs via [GitHub issues](https://github.com/thehapyone/Mergebot/issues)

---

Thank you for contributing to Mergebot! 🚀
