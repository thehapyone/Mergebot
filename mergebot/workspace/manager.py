"""Workspace manager for context-aware reviews.

Provisions a per-review clone of the PR/MR head with a hard security boundary
(see docs/proposals/context-aware-review-architecture.md section 3.1):

- shallow, blobless clone at a head SHA into a per-review temp workspace
- split-jail layout: `<root>/checkout/` is the only directory tools may read;
  `<root>/secrets/` (askpass helper) sits OUTSIDE that jail
- the token reaches git only as a process env var read by a secret-free askpass
  helper — never URL, argv, `.git/config`, or disk
- a base-SHA guarantee so diffing/CRG have the base commit available
- preflight checks (repo size + room for this clone)
- graceful degradation: any failure returns a degraded workspace, never raises
- cleanup in the caller's `finally` plus a TTL-based orphan sweeper

Git runs via `asyncio.create_subprocess_exec` (argument lists, never shell).

Container deployment is configure-don't-detect: the Dockerfile installs git + ripgrep +
code-review-graph and points MERGEBOT_WORKSPACE_DIR at a disk-backed, writable volume.
"""

import asyncio
import contextlib
import json
import os
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mergebot.validator.logging_config import logger

_FALLBACK_ROOT = Path(tempfile.gettempdir()) / "mergebot" / "workspaces"
DEFAULT_ROOT_DIR = Path(os.getenv("MERGEBOT_WORKSPACE_DIR", str(_FALLBACK_ROOT)))
DEFAULT_CLONE_TIMEOUT = 120
DEFAULT_DEPTH = 50
DEFAULT_MAX_REPO_MB = 2048
ORPHAN_TTL_SECONDS = 6 * 60 * 60
SWEEP_INTERVAL_SECONDS = 15 * 60

# Network/TLS env passed through to git so clones work behind corporate proxies and
# TLS-intercepting CAs (the API side already honors these via requests).
GIT_NETWORK_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "GIT_SSL_CAINFO",
    "GIT_SSL_CAPATH",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "CURL_CA_BUNDLE",
)

# Always-on git safety flags: never run repo hooks, no fsmonitor daemon, no risky
# transports, never block on an interactive credential prompt, and never
# materialize PR-controlled symlinks (they become plain files holding the target
# path, so nothing that reads the checkout can be routed outside it).
GIT_SAFETY_CONFIG = [
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "protocol.ext.allow=never",
    "-c",
    "core.symlinks=false",
]


class WorkspaceError(RuntimeError):
    """Raised for unrecoverable workspace failures (preflight is non-raising)."""


class PathJailError(RuntimeError):
    """Raised when a requested path escapes the checkout jail."""


@dataclass(frozen=True)
class PrRef:
    """Structured PR metadata supplied by the platform API wrappers (proposal 3.1)."""

    clone_url: str
    head_sha: str
    base_sha: str | None = None
    pr_number: int | None = None
    fetch_ref: str | None = None  # refs/pull/<n>/head or refs/merge-requests/<n>/head
    repo_size_kb: int | None = None


@dataclass(frozen=True)
class GitCredential:
    """A git-usable HTTPS credential. Mergebot already has this — no new secret.

    Built from the existing `ProjectRuntime` auth (see `credential_from_runtime`):
    GitHub App installation token or PAT (username `x-access-token`), or a GitLab PAT
    (username `oauth2`). The same credential Mergebot uses to review/comment/approve.
    """

    username: str  # "x-access-token" (GitHub) | "oauth2" (GitLab)
    token: str


@dataclass(frozen=True)
class WorkspaceLimits:
    root_dir: Path = DEFAULT_ROOT_DIR
    clone_timeout: int = DEFAULT_CLONE_TIMEOUT
    depth: int = DEFAULT_DEPTH
    max_repo_mb: int = DEFAULT_MAX_REPO_MB
    # Fan-out (workers x max_concurrency concurrent clones) is sized by the deploy — the
    # container's workspace volume is provisioned for it. At runtime we only guard that
    # THIS clone has room, so the headroom factor stays small.


@dataclass
class Workspace:
    root: Path
    checkout: Path
    secrets_dir: Path
    head_sha: str
    base_sha: str | None = None
    pr_number: int | None = None
    degraded: bool = False
    degraded_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # The isolated git env (incl. the token) persisted for the workspace lifetime, so
    # blobless lazy-fetches during later tool calls can still authenticate. repr=False
    # and never copied into `metadata` so the token is not accidentally logged.
    git_env: dict[str, str] = field(default_factory=dict, repr=False)

    @property
    def base_present(self) -> bool:
        return bool(self.metadata.get("base_present"))

    def resolve_in_checkout(self, path: str | Path) -> Path:
        """Resolve a tool-supplied path, refusing anything outside the checkout jail.

        This is the single chokepoint every read-only exploration tool must call.
        It resolves symlinks before the containment check, so a symlink inside the
        checkout that points at `../secrets` (or anywhere else) is rejected.
        """
        checkout_real = self.checkout.resolve()
        raw = Path(path)
        candidate = raw if raw.is_absolute() else (self.checkout / raw)
        real = candidate.resolve()
        if real != checkout_real and not real.is_relative_to(checkout_real):
            raise PathJailError(f"path escapes checkout jail: {path}")
        rel_parts = real.relative_to(checkout_real).parts if real != checkout_real else ()
        if ".git" in rel_parts:
            raise PathJailError(f"path targets .git internals: {path}")
        return real


class WorkspaceManager:
    def __init__(self, limits: WorkspaceLimits | None = None) -> None:
        self.limits = limits or WorkspaceLimits()
        self.limits.root_dir.mkdir(parents=True, exist_ok=True)

    # -- public API ---------------------------------------------------------------

    async def provision(self, pr: PrRef, credential: GitCredential | None = None) -> Workspace:
        """Provision a workspace for one review. Never raises: failures degrade."""
        preflight = self._preflight(pr)
        if preflight is not None:
            return self._degraded(reason=preflight, pr=pr)

        root = Path(
            tempfile.mkdtemp(
                prefix=f"mergebot-pr{pr.pr_number or 'x'}-",
                dir=str(self.limits.root_dir),
            )
        )
        checkout = root / "checkout"
        secrets_dir = root / "secrets"
        secrets_dir.mkdir(mode=0o700)
        (root / ".mergebot-workspace").write_text(
            json.dumps({"created_at": int(time.time()), "pr": pr.pr_number}),
            encoding="utf-8",
        )

        env = self._git_env(secrets_dir, credential)
        try:
            await self._clone(pr, checkout, env)
            await self._ensure_ref(pr.head_sha, checkout, env, pr)
            base_present = await self._ensure_base(pr, checkout, env)
            await self._checkout_sha(pr.head_sha, checkout, env)
        except WorkspaceError as exc:
            await self.cleanup(
                Workspace(
                    root=root, checkout=checkout, secrets_dir=secrets_dir, head_sha=pr.head_sha
                )
            )
            return self._degraded(reason=str(exc), pr=pr)

        return Workspace(
            root=root,
            checkout=checkout,
            secrets_dir=secrets_dir,
            head_sha=pr.head_sha,
            base_sha=pr.base_sha,
            pr_number=pr.pr_number,
            git_env=env,  # persisted for the workspace lifetime (lazy-fetch auth)
            metadata={
                "depth": self.limits.depth,
                "base_present": base_present,
                "auth": credential.username if credential else "anonymous",
                "root_dir": str(self.limits.root_dir),
            },
        )

    async def cleanup(self, ws: Workspace) -> None:
        await asyncio.to_thread(shutil.rmtree, ws.root, ignore_errors=True)

    # Process-wide sweep throttle (class attribute, shared by all manager instances).
    _last_sweep_at: float | None = None

    async def sweep_orphans(self, ttl_seconds: int = ORPHAN_TTL_SECONDS) -> list[str]:
        """Remove workspaces older than the TTL (crash-safety, no external infra).

        Throttled process-wide: concurrent reviews all sweep the same root, so one
        pass per interval is enough and avoids racing rmtree on the same orphan.
        """
        now = time.monotonic()
        last = WorkspaceManager._last_sweep_at
        if last is not None and now - last < SWEEP_INTERVAL_SECONDS:
            return []
        WorkspaceManager._last_sweep_at = now
        return await asyncio.to_thread(self._sweep_orphans_sync, ttl_seconds)

    def _sweep_orphans_sync(self, ttl_seconds: int) -> list[str]:
        removed = []
        now = time.time()
        for child in self.limits.root_dir.glob("mergebot-pr*"):
            marker = child / ".mergebot-workspace"
            try:
                created = json.loads(marker.read_text(encoding="utf-8")).get("created_at", 0)
            except (OSError, ValueError):
                created = child.stat().st_mtime
            if now - created > ttl_seconds:
                shutil.rmtree(child, ignore_errors=True)
                removed.append(str(child))
        if removed:
            logger.info("Workspace sweeper removed %d orphaned workspace(s).", len(removed))
        return removed

    # -- preflight ----------------------------------------------------------------

    def _preflight(self, pr: PrRef) -> str | None:
        """Return a reason string if the enriched path should be skipped, else None."""
        root = self.limits.root_dir
        if not os.access(root, os.W_OK):
            return f"root_dir not writable: {root}"
        if pr.repo_size_kb is not None and pr.repo_size_kb / 1024 > self.limits.max_repo_mb:
            return f"repo too large: {pr.repo_size_kb / 1024:.0f}MB > {self.limits.max_repo_mb}MB"
        # Room for THIS clone (working tree + .git ≈ 2x repo size). Volume-level sizing
        # for concurrent reviews is a deploy concern, not a runtime check.
        needed_mb = self.limits.max_repo_mb * 2
        free_mb = shutil.disk_usage(root).free / (1024 * 1024)
        if free_mb < needed_mb:
            return f"insufficient disk: {free_mb:.0f}MB free < {needed_mb}MB needed for this clone"
        return None

    # -- git plumbing -------------------------------------------------------------

    async def _clone(self, pr: PrRef, checkout: Path, env: dict[str, str]) -> None:
        await self._git(
            [
                "clone",
                # Persisted into the new repo's config (unlike the per-invocation
                # GIT_SAFETY_CONFIG flags), so git run by the context builder and
                # CRG inside the checkout sees the same no-symlinks semantics.
                "-c",
                "core.symlinks=false",
                "--filter=blob:none",
                "--no-tags",
                "--no-checkout",
                f"--depth={self.limits.depth}",
                pr.clone_url,
                str(checkout),
            ],
            env=env,
            cwd=self.limits.root_dir,
            what="clone",
        )

    async def _ensure_ref(self, sha: str, checkout: Path, env: dict[str, str], pr: PrRef) -> None:
        # Prefer the PR ref (works for forks without fork credentials); fall back to SHA.
        if pr.fetch_ref:
            returncode, _, _ = await self._git(
                ["fetch", f"--depth={self.limits.depth}", "origin", pr.fetch_ref],
                env=env,
                cwd=checkout,
                what="fetch-pr-ref",
                check=False,
            )
            if returncode == 0:
                return
        await self._git(
            ["fetch", f"--depth={self.limits.depth}", "origin", sha],
            env=env,
            cwd=checkout,
            what="fetch-head-sha",
            check=False,
        )

    async def _ensure_base(self, pr: PrRef, checkout: Path, env: dict[str, str]) -> bool:
        """Best-effort: make sure the base commit is in history for diff/CRG."""
        if not pr.base_sha:
            return False
        if await self._has_commit(pr.base_sha, checkout, env):
            return True
        await self._git(
            ["fetch", f"--depth={self.limits.depth}", "origin", pr.base_sha],
            env=env,
            cwd=checkout,
            what="fetch-base",
            check=False,
        )
        return await self._has_commit(pr.base_sha, checkout, env)

    async def _checkout_sha(self, sha: str, checkout: Path, env: dict[str, str]) -> None:
        await self._git(["checkout", "--detach", sha], env=env, cwd=checkout, what="checkout")

    async def _has_commit(self, sha: str, checkout: Path, env: dict[str, str]) -> bool:
        returncode, _, _ = await self._git(
            ["cat-file", "-e", f"{sha}^{{commit}}"],
            env=env,
            cwd=checkout,
            what="has-commit",
            check=False,
        )
        return returncode == 0

    async def _git(
        self,
        args: list[str],
        env: dict[str, str],
        cwd: Path,
        what: str,
        check: bool = True,
    ) -> tuple[int, str, str]:
        """Run one git command; returns (returncode, stdout, stderr)."""
        process = await asyncio.create_subprocess_exec(
            "git",
            *GIT_SAFETY_CONFIG,
            *args,
            cwd=str(cwd),
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                process.communicate(), timeout=self.limits.clone_timeout
            )
        except TimeoutError:
            process.kill()
            with contextlib.suppress(Exception):
                await process.communicate()
            raise WorkspaceError(
                f"git {what} timed out after {self.limits.clone_timeout}s"
            ) from None
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        if check and process.returncode != 0:
            raise WorkspaceError(f"git {what} failed ({process.returncode}): {stderr.strip()}")
        return process.returncode, stdout, stderr

    # -- credentials --------------------------------------------------------------

    def _git_env(self, secrets_dir: Path, credential: GitCredential | None) -> dict[str, str]:
        """Build the git env. The token (if any) lives ONLY here, never on disk.

        HOME → secrets_dir gives git a writable, empty home (important in a container
        where the app user's HOME may be unset/non-writable), and incidentally means no
        global ~/.gitconfig credential helper can cache the token. GIT_TERMINAL_PROMPT=0
        guarantees a missing credential degrades instead of hanging.
        """
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": str(secrets_dir),
        }
        for var in GIT_NETWORK_ENV_VARS:
            if var in os.environ:
                env[var] = os.environ[var]
        if credential is not None:
            askpass = self._write_askpass_helper(secrets_dir)
            env["GIT_ASKPASS"] = str(askpass)
            env["MERGEBOT_GIT_USERNAME"] = credential.username  # x-access-token | oauth2
            env["MERGEBOT_GIT_TOKEN"] = credential.token  # process env only — not argv/config
        return env

    @staticmethod
    def _write_askpass_helper(secrets_dir: Path) -> Path:
        """A SECRET-FREE helper: it echoes the token from the env, not from disk."""
        helper = secrets_dir / "askpass.sh"
        helper.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            '  Username*) printf "%s" "${MERGEBOT_GIT_USERNAME:-x-access-token}" ;;\n'
            '  *) printf "%s" "${MERGEBOT_GIT_TOKEN}" ;;\n'
            "esac\n",
            encoding="utf-8",
        )
        helper.chmod(stat.S_IRWXU)  # 0700, owner-only
        return helper

    # -- helpers ------------------------------------------------------------------

    def _degraded(self, reason: str, pr: PrRef) -> Workspace:
        logger.warning(
            "Workspace degraded for PR/MR %s: %s (falling back to diff-only review)",
            pr.pr_number if pr.pr_number is not None else "?",
            reason,
        )
        placeholder = self.limits.root_dir / "__degraded__"
        return Workspace(
            root=placeholder,
            checkout=placeholder,
            secrets_dir=placeholder,
            head_sha=pr.head_sha,
            base_sha=pr.base_sha,
            pr_number=pr.pr_number,
            degraded=True,
            degraded_reason=reason,
        )


def credential_from_runtime(platform: str, token: str) -> GitCredential:
    """Map Mergebot's already-resolved auth to a git-usable credential.

    Callers pass the token the api_wrapper already resolved/minted from the
    `ProjectRuntime`: a GitHub App installation token (`_get_installation_token`) or a
    GitHub PAT (`GITHUB_TOKEN`) → username `x-access-token`; or a GitLab PAT
    (`GITLAB_PERSONAL_ACCESS_TOKEN`) → username `oauth2`. The clone reuses the SAME
    credential Mergebot already uses to review/comment/approve — no new secret. It is
    safe to hand this (push-capable) token to the workspace precisely because the
    split-jail keeps it unreachable from the read-only reviewer tools. App installation
    tokens are short-lived (~1h); the manager takes a freshly-resolved one per review and
    never caches it across reviews.
    """
    username = "oauth2" if platform.lower().startswith("gitlab") else "x-access-token"
    return GitCredential(username=username, token=token)
