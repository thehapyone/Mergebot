# Mergebot Coding Guideline

Use this file for code style and implementation conventions.

## Guiding Principles

- Prefer repo-local patterns over generic preferences.
- Keep changes focused and avoid speculative abstraction.
- Fix source-of-truth contracts instead of patching symptoms around bad inputs.
- Preserve GitHub and GitLab parity unless a change is explicitly platform-specific.
- Treat docs and configuration as part of the implementation when behavior changes.
- Do not add AI attribution or AI-generated fingerprints to code, docs, commits, or PRs.

## Tooling

Use the configured Poetry, Ruff, Codespell, and pre-commit setup. Do not add another
formatter, linter, type checker, or package manager unless that is the explicit task.

## Python Style

- Use `snake_case` for modules, functions, variables, and methods.
- Use `PascalCase` for classes.
- Use `UPPER_CASE` only for true module-level constants.
- Use lowercase class attributes unless they are real constants; use `ClassVar[...]`
  for typed class constants on Pydantic models or wrapper classes.
- Keep imports sorted by Ruff.
- Prefer modern type syntax: `str | None`, `list[str]`, `dict[str, Any]`.
- Do not add `from __future__ import annotations`; the project uses a modern Python
  version, so use native annotations directly. If a forward reference is unavoidable,
  quote that one annotation instead.
- Use `Field(default_factory=...)` or dataclass factories for mutable defaults.
- Keep helper functions private with a leading underscore when they are module-local.
- Keep comments sparse and explanatory. Do not narrate obvious assignments.

Prefer concise, public-facing docstrings for modules, classes, and public functions.
Use Google-style sections (`Args:`, `Returns:`, `Raises:`) when a function has
non-obvious inputs, return shape, or failure modes. Internal helpers can have short
docstrings or no docstring if their name and context are clear.

## Types and Data Models

Use Pydantic at boundaries and dataclasses for internal value objects.

- Config models should inherit from `StrictBaseModel` when extra keys must be rejected.
- API/tool schemas should use Pydantic `BaseModel` with `Field(...)` descriptions.
- Runtime-only value carriers can use `@dataclass(slots=True)` or frozen dataclasses.
- Validate external input at the boundary. Avoid repeated defensive validation between
  trusted internal functions unless the boundary is unclear.
- Fail fast on missing required config, invalid project definitions, unsupported VCS
  types, malformed webhook config, and missing credentials.

For new config:

- Add a typed model in `mergebot/validator/config.py`.
- Use clear defaults only when the safe behavior is obvious.
- Document new config in `docs/configuration/`.
- Keep secrets in environment variables or secret stores, never in tracked examples.
- Update example configs when the user-facing shape changes.

## Architecture Conventions

### Flow and services

Keep orchestration, side effects, and platform calls separated.

- Flow code should orchestrate steps, collect state, and delegate work.
- Services should own business decisions and external side-effect coordination.
- Platform wrappers should own GitHub/GitLab API details.
- Tool classes should be thin adapters over wrappers and runtime context.

Pass `ProjectRuntime` explicitly through service and tool calls. Avoid hidden global
configuration or module-level runtime state.

### Platform parity

- Keep platform-specific code behind wrappers or explicit runtime dispatch.
- Use `runtime.platform_type` only at platform selection boundaries.
- Keep shared shape names neutral where possible: PR/MR, pull or merge request,
  source branch, target branch, status, approval state, CI state.
- Normalize platform-specific payloads before handing them to flow, services, crews,
  dashboard, or decision logic.
- If a capability is not available on one platform, make that limitation explicit and
  degrade safely.

### Crews and prompts

- Add new analysis concerns as a new crew only when it has a distinct responsibility.
- Keep `crew.py` small and declarative; put agent/task text in YAML config.
- Use the shared `BotBaseCrew` pattern for LLM setup.
- Keep prompt outputs deterministic enough for downstream parsing or typed validation.
- Prefer typed structured outputs for new crew contracts when feasible.

### Dashboard and session state

- Preserve dashboard markers and bounded sections.
- Update only the section a feature owns.
- Keep session lock writes idempotent and owner/nonce-aware.
- Avoid introducing external infrastructure for coordination unless required.

## External Calls and Reliability

Network and VCS calls must be bounded, observable, and retry-aware.

- Always set request timeouts for `requests.get()` and `requests.post()`.
- Handle pagination for GitHub/GitLab endpoints that can return many items.
- Use `ServiceError` and `async_retry` for short, idempotent service operations.
- Do not retry large or unsafe writes unless the operation has an idempotency guard.
- Log failures with enough context to debug the project, PR/MR, run, page, or job.
- Avoid loading large CI logs fully into memory; stream or keep a bounded tail.

## Async and Concurrency

- Keep async flow methods async all the way down where practical.
- Do not block the event loop with slow filesystem, VCS, or network operations.
- Use `asyncio.to_thread` for unavoidable blocking work inside async orchestration.
- Use semaphores or explicit concurrency limits for multi-project or multi-PR runners.
- Ensure background tasks such as heartbeats are stopped in `finally` paths.

## Logging

Use Mergebot's shared logger:

```python
from mergebot.validator.logging_config import logger
```

- Prefer structured, specific messages over generic "failed" logs.
- Use `logger.info` for lifecycle events, `logger.warning` for recoverable external
  failures, and `logger.error` for final failures.
- Use `exc_info=True` where a stack trace is useful and not noisy.
- Avoid `print()` except for deliberate CLI output.
- Never log tokens, private keys, webhook secrets, or raw secret-bearing config.

## Testing

- Add tests for new behavior, bug fixes, parsing rules, scoring rules, config models,
  retry behavior, and platform normalization.
- Name test files `test_<module>.py`.
- Keep unit tests offline by mocking GitHub, GitLab, LLM, and network services.
- Test error paths: missing config, invalid YAML, API failures, pagination edges,
  inconclusive analysis, merge guardrail failures, and lock contention.
- For async code, use explicit async tests and deterministic sleeps/mocks.
- Cross-platform behavior: verify both GitHub and GitLab paths by unit test, fixture,
  or clearly stated manual evidence.

## Documentation

- Update docs when a code change alters user-visible behavior, config keys, CLI flags,
  environment variables, dashboard markers, or operational commands.
- Keep docs concise and source-of-truth oriented.
- Remove stale assumptions instead of layering contradictory notes.

## Dependencies

- Add runtime dependencies only when the standard library or existing packages are not
  adequate.
- Prefer established packages already present in the stack: Pydantic, PyGitHub,
  python-gitlab, CrewAI, FastAPI, YAML tooling, and Requests.
- Keep dependency changes small and explain why they are needed.
- After dependency changes, update `poetry.lock` and run the relevant checks.

## Security

- Keep credentials in environment variables or secret stores.
- Validate GitHub HMAC signatures and GitLab webhook tokens through config-driven
  secrets.
- Treat repository contents, CI logs, PR bodies, and comments as untrusted input.
- Avoid shelling out with unsanitized user or repository-provided strings.
- Do not write secrets into dashboard issues, PR comments, logs, examples, or docs.
- Prefer deny-by-default config models (`extra="forbid"`) for security-sensitive input.

## Review Checklist

Before finishing a change, check:

- Does it follow the existing module boundary?
- Is GitHub/GitLab parity preserved or explicitly handled?
- Is config typed, validated, documented, and safe by default?
- Are external calls timeout-bound and paginated where needed?
- Are retries limited to safe/idempotent operations?
- Are logs useful and secret-safe?
- Are tests added or updated for the changed behavior?
- Did documentation or examples need an update?
