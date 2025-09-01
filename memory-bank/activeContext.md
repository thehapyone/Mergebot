# Active Context

## Current Work Focus

- Implemented a stateless, project-scoped “session lock” to prevent concurrent Mergebot runs against the same repository.
- The lock is persisted inside the Dashboard issue under a single “Active Session” header and bounded by `<!-- marker:MERGEBOT_SESSION_LOCK -->` markers.
- The session lock has a default TTL of 10 minutes and is refreshed by a heartbeat during active runs.
- Integrated the lock in both ondemand and webhook flows so they mutually respect the same project session.
- Fixed Dashboard layout/duplication issues so only one “Active Session” header renders; the lock updater only replaces content between markers.

## Recent Changes

### Code
- mergebot/dashboard/dashboard_layout.md
  - Added the “Active Session” section (header + markers + `{{ locks_section }}`).
- mergebot/dashboard/dashboard_manager.py
  - Added `SESSION_LOCK_MARKER`.
  - `_generate_dashboard_body` now extracts the existing lock section from the current Dashboard and passes it to the template as `locks_section`, preserving lock content on re-renders.
- mergebot/dashboard/session_lock.py (new)
  - `SessionLockCoordinator`:
    - `try_acquire()` performs optimistic acquire by write-then-verify (nonce check).
    - `start_heartbeat()` / `stop_heartbeat()` refresh TTL while a run is active.
    - `release()` removes the lock if owned.
    - Replaces only content between markers; never inserts the section header to avoid duplication.
    - Normalizes placement inside the main dashboard region before the Analytics header if needed.
  - Defaults:
    - TTL = 600s (10 minutes)
    - Refresh interval = max(30s, TTL/3) ~ 200s
    - Owner ID = `hostname-pid-uuid`
- mergebot/ondemand_runner.py
  - Acquires project session lock at the start of `run_once()`. If acquisition fails, logs and returns without running analysis; otherwise starts heartbeat and releases after update.
- mergebot/webhook_server.py
  - Wraps `run_flow` in `analyze_with_session_lock()` so webhook-triggered runs also respect the same project session lock.

### Docs
- docs/architecture/dashboard.md
  - Added “Project-level Session Lock” section (storage, TTL, owner, behavior).
- docs/architecture/ondemand_runner.md
  - Added “Project Session Lock” section (scope, storage, TTL, crash safety).
- docs/usage/running.md
  - Added “Project Session Lock” runtime behavior and expectations for users.
- docs/operations/docker_compose.md
  - Added “Session Lock Notes” including log examples and env vars.
- docs/capabilities.md
  - Added capability: “Project-level session lock to prevent concurrent runs per repository.”

## Important Decisions & Patterns

- Project-level session lock (not per-MR):
  - Prevents entire overlapping sessions (ondemand scans or webhook-driven runs) for the same project, which avoids duplicate dashboard writes and comments.
- Dashboard-backed persistence:
  - No external infra required (stateless). Lock lives in the project Dashboard body.
  - Verify-after-write (nonce) removes ambiguity when multiple instances race to acquire.
- One canonical header:
  - The Dashboard template owns the header. The lock coordinator ONLY updates the content between markers to avoid header duplication.
- Safe TTL handling:
  - TTL ensures a crashed process won’t block future runs; heartbeat extends during long sessions.

## Known Issues / Considerations

- Platform rate limits & eventual consistency:
  - Multiple quick successive updates to the issue body could race or be throttled. The current approach re-reads after updates for verification and places the lock in a canonical position.
- Layout drift on legacy dashboards:
  - The lock updater now normalizes placement under the main dashboard region; if markers are missing, it inserts a markers-only block and relies on the template header.
- Observability:
- Config knobs:
  - TTL and refresh interval are coded defaults (10m, ~200s). If needed, future work could add config fields and validation.

## Next Steps

- Add tests for SessionLockCoordinator:
  - Acquire/release/heartbeat flows, race scenarios, expired lock takeover, and normalization behavior.
- Optional configuration:
  - Expose `lock.ttl_seconds` and `lock.refresh_interval_seconds` in the config schema if users request tunables.
- Operational hardening:
  - Backoff and retry strategies around dashboard update failures (rate limits, transient network issues).
- Telemetry / Analytics:
  - Emit simple metrics/logs for lock lifecycle events to aid in troubleshooting.

## Project Insights

- The dashboard-embedded session lock strikes a balance between “no external dependencies” and “safe concurrency”.
- A per-MR lock could be added later if we converge on a use case where multiple MRs must be processed concurrently across instances; for now, one project session is the right granularity to avoid duplicate comments/analytics.
