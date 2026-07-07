"""Workspace-manager prototype for Mergebot.

This module is intentionally standalone: it does not alter the production flow. It is a
proving ground for the workspace/security boundary described in
`docs/proposals/context-aware-review-architecture.md` (section 3.1) before we commit to
the full flow integration.

What it demonstrates:
- shallow, blobless clone at a head SHA into a per-review temp workspace
- a split-jail layout: `<root>/checkout/` is the only directory tools may read;
  `<root>/secrets/` (askpass helper) sits OUTSIDE that jail
- credential handling that keeps the token out of argv, `.git/config`, and the jail
  (the askpass helper is secret-free; the token lives only in the git child's env)
- a base-SHA guarantee so CRG `detect-changes` has the base commit available
- preflight checks (repo size + room for this clone)
- graceful degradation: any failure returns a degraded workspace, never raises
- a path-jail resolver + a self-test that asserts the security properties hold

Container deployment: Mergebot ships as a Docker image, so environment facts the image
controls are configured at build time, not detected at runtime — the Dockerfile installs
git + ripgrep + code-review-graph and points MERGEBOT_WORKSPACE_DIR at a disk-backed,
writable volume sized for the configured review fan-out (workers x max_concurrency).

The production version (`mergebot/workspace/manager.py`) will run git via
`asyncio.create_subprocess_exec`; this prototype is synchronous for easy CLI testing.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROTOTYPE_VERSION = "0.2"
# Mergebot runs as a Docker container, so the workspace path is something the IMAGE
# defines, not something we detect at runtime. The Dockerfile points
# MERGEBOT_WORKSPACE_DIR at a disk-backed, writable volume (never a tmpfs/ramfs mount)
# and installs git + ripgrep + code-review-graph. We just trust that path here.
_FALLBACK_ROOT = Path(tempfile.gettempdir()) / "mergebot" / "workspaces"
DEFAULT_ROOT_DIR = Path(os.getenv("MERGEBOT_WORKSPACE_DIR", str(_FALLBACK_ROOT)))
DEFAULT_CLONE_TIMEOUT = 120
DEFAULT_DEPTH = 50
DEFAULT_MAX_REPO_MB = 2048
ORPHAN_TTL_SECONDS = 6 * 60 * 60

# Always-on git safety flags: never run repo hooks, no fsmonitor daemon, no risky
# transports, and never block on an interactive credential prompt.
GIT_SAFETY_CONFIG = [
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "protocol.ext.allow=never",
]


class WorkspaceError(RuntimeError):
    """Raised for unrecoverable workspace failures (preflight is non-raising)."""


class PathJailError(RuntimeError):
    """Raised when a requested path escapes the checkout jail."""


@dataclass(frozen=True)
class PrRef:
    """The structured PR metadata the production wrappers will supply (proposal 3.1)."""

    clone_url: str
    head_sha: str
    base_sha: str | None = None
    pr_number: int | None = None
    fetch_ref: str | None = None  # refs/pull/<n>/head or refs/merge-requests/<n>/head
    repo_size_kb: int | None = None


@dataclass(frozen=True)
class GitCredential:
    """A git-usable HTTPS credential. Mergebot already has this — no new secret.

    Production builds it from the existing `ProjectRuntime` auth (see
    `credential_from_runtime` below): GitHub App installation token or PAT
    (username `x-access-token`), or a GitLab PAT (username `oauth2`). The same
    credential Mergebot uses to review/comment/approve/push the onboarding MR.
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

    def provision(self, pr: PrRef, credential: GitCredential | None = None) -> Workspace:
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
            self._clone(pr, checkout, env)
            self._ensure_ref(pr.head_sha, checkout, env, pr)
            base_present = self._ensure_base(pr, checkout, env)
            self._checkout_sha(pr.head_sha, checkout, env)
        except WorkspaceError as exc:
            self.cleanup(
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
                "prototype_version": PROTOTYPE_VERSION,
                "depth": self.limits.depth,
                "base_present": base_present,
                "auth": credential.username if credential else "anonymous",
                "root_dir": str(self.limits.root_dir),
            },
        )

    def cleanup(self, ws: Workspace) -> None:
        shutil.rmtree(ws.root, ignore_errors=True)

    def sweep_orphans(self, ttl_seconds: int = ORPHAN_TTL_SECONDS) -> list[str]:
        """Remove workspaces older than the TTL (crash-safety, no external infra)."""
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

    def _clone(self, pr: PrRef, checkout: Path, env: dict[str, str]) -> None:
        self._git(
            [
                "clone",
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

    def _ensure_ref(self, sha: str, checkout: Path, env: dict[str, str], pr: PrRef) -> None:
        # Prefer the PR ref (works for forks without fork credentials); fall back to SHA.
        if pr.fetch_ref:
            res = self._git(
                ["fetch", f"--depth={self.limits.depth}", "origin", pr.fetch_ref],
                env=env,
                cwd=checkout,
                what="fetch-pr-ref",
                check=False,
            )
            if res.returncode == 0:
                return
        self._git(
            ["fetch", f"--depth={self.limits.depth}", "origin", sha],
            env=env,
            cwd=checkout,
            what="fetch-head-sha",
            check=False,
        )

    def _ensure_base(self, pr: PrRef, checkout: Path, env: dict[str, str]) -> bool:
        """Best-effort: make sure the base commit is in history for diff/CRG."""
        if not pr.base_sha:
            return False
        if self._has_commit(pr.base_sha, checkout, env):
            return True
        self._git(
            ["fetch", f"--depth={self.limits.depth}", "origin", pr.base_sha],
            env=env,
            cwd=checkout,
            what="fetch-base",
            check=False,
        )
        return self._has_commit(pr.base_sha, checkout, env)

    def _checkout_sha(self, sha: str, checkout: Path, env: dict[str, str]) -> None:
        self._git(["checkout", "--detach", sha], env=env, cwd=checkout, what="checkout")

    def _has_commit(self, sha: str, checkout: Path, env: dict[str, str]) -> bool:
        res = self._git(
            ["cat-file", "-e", f"{sha}^{{commit}}"],
            env=env,
            cwd=checkout,
            what="has-commit",
            check=False,
        )
        return res.returncode == 0

    def _git(
        self,
        args: list[str],
        env: dict[str, str],
        cwd: Path,
        what: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *GIT_SAFETY_CONFIG, *args],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.limits.clone_timeout,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        if check and result.returncode != 0:
            raise WorkspaceError(
                f"git {what} failed ({result.returncode}): {result.stderr.strip()}"
            )
        return result

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
            metadata={"prototype_version": PROTOTYPE_VERSION},
        )


def credential_from_runtime(platform: str, token: str) -> GitCredential:
    """Map Mergebot's already-resolved auth to a git-usable credential (integration contract).

    Production passes the token the api_wrapper already resolved/minted from the
    `ProjectRuntime`: a GitHub App installation token (`_get_installation_token`) or a
    GitHub PAT (`GITHUB_TOKEN`) → username `x-access-token`; or a GitLab PAT
    (`GITLAB_PERSONAL_ACCESS_TOKEN`) → username `oauth2`. The clone reuses the SAME
    credential Mergebot already uses to review/comment/approve/push — no new secret. It
    is safe to hand this (push-capable) token to the workspace precisely because the
    split-jail keeps it unreachable from the read-only reviewer tools. App installation
    tokens are short-lived (~1h); the manager takes a freshly-resolved one per review and
    never caches it across reviews.
    """
    username = "oauth2" if platform.lower().startswith("gitlab") else "x-access-token"
    return GitCredential(username=username, token=token)


# -- self-test / demo -------------------------------------------------------------


def _token_leak_scan(checkout: Path, token: str) -> list[str]:
    """Return any tool-readable locations under the checkout where the token appears."""
    hits = []
    for path in checkout.rglob("*"):
        if not path.is_file():
            continue
        # .git is excluded from tool reads, but scan it too to prove the token
        # isn't even cached in config/credentials.
        try:
            if token in path.read_text(encoding="utf-8", errors="ignore"):
                hits.append(str(path.relative_to(checkout)))
        except OSError:
            continue
    return hits


def _security_checks(
    manager: WorkspaceManager, ws: Workspace, credential: GitCredential | None
) -> list[dict[str, Any]]:
    """The shared security assertions, run against any provisioned (non-degraded) ws."""
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": ok, "detail": detail})

    env = ws.git_env  # the persisted, workspace-lifetime env (incl. token)

    record(
        "secrets_dir is OUTSIDE the checkout jail",
        not ws.secrets_dir.resolve().is_relative_to(ws.checkout.resolve()),
        f"secrets={ws.secrets_dir.name}/ checkout={ws.checkout.name}/",
    )

    if credential is not None:
        token = credential.token
        leaks = _token_leak_scan(ws.checkout, token)
        record("token absent from everything under checkout (incl. .git)", not leaks, str(leaks))
        cfg = manager._git(
            ["config", "--list", "--show-origin"],
            env=env,
            cwd=ws.checkout,
            what="config",
            check=False,
        ).stdout
        record("token absent from git config", token not in cfg)
        helper = ws.secrets_dir / "askpass.sh"
        record(
            "askpass helper is secret-free (token only in process env)",
            helper.exists() and token not in helper.read_text(encoding="utf-8"),
        )
        record(
            "askpass helper is owner-only (0700)",
            helper.exists() and stat.S_IMODE(helper.stat().st_mode) == 0o700,
            oct(stat.S_IMODE(helper.stat().st_mode)) if helper.exists() else "missing",
        )

    hooks = manager._git(
        ["config", "--get", "core.hooksPath"],
        env=env,
        cwd=ws.checkout,
        what="hooks",
        check=False,
    ).stdout.strip()
    record(
        "hooks neutralized (core.hooksPath=/dev/null)",
        hooks in {"", "/dev/null"},
        f"persisted config value: {hooks or '(per-invocation -c)'}",
    )

    real_file = next((p for p in ws.checkout.rglob("*") if p.is_file()), None)
    if real_file:
        resolved = ws.resolve_in_checkout(real_file.relative_to(ws.checkout))
        record("path jail allows a real file inside checkout", resolved.exists())

    evil = ws.checkout / "evil-link"
    try:
        evil.symlink_to(ws.secrets_dir)
        try:
            ws.resolve_in_checkout("evil-link/askpass.sh")
            record("path jail rejects symlink escape to secrets/", False, "NOT rejected!")
        except PathJailError:
            record("path jail rejects symlink escape to secrets/", True)
    finally:
        evil.unlink(missing_ok=True)

    for label, bad_path in [
        ("path jail rejects ../ traversal", "../secrets/askpass.sh"),
        ("path jail rejects absolute path outside checkout", "/etc/passwd"),
        ("path jail rejects .git internals", ".git/config"),
    ]:
        try:
            ws.resolve_in_checkout(bad_path)
            record(label, False, "NOT rejected!")
        except PathJailError:
            record(label, True)

    return checks


def _collect_clone_facts(manager: WorkspaceManager, ws: Workspace) -> dict[str, Any]:
    env = ws.git_env
    head = manager._git(
        ["rev-parse", "HEAD"], env=env, cwd=ws.checkout, what="rev-parse", check=False
    ).stdout.strip()
    count = manager._git(
        ["rev-list", "--count", "HEAD"], env=env, cwd=ws.checkout, what="count", check=False
    ).stdout.strip()
    pfilter = manager._git(
        ["config", "--get", "remote.origin.partialclonefilter"],
        env=env,
        cwd=ws.checkout,
        what="filter",
        check=False,
    ).stdout.strip()
    worktree_files = sum(
        1
        for p in ws.checkout.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(ws.checkout).parts
    )
    git_dir_kb = (
        sum(f.stat().st_size for f in (ws.checkout / ".git").rglob("*") if f.is_file()) // 1024
    )
    return {
        "head_checked_out": head,
        "shallow_clone": (ws.checkout / ".git" / "shallow").exists(),
        "shallow_commit_count": count,
        "partial_clone_filter": pfilter or "(none)",
        "worktree_files": worktree_files,
        "git_dir_kb": git_dir_kb,
    }


def provision_report(
    pr: PrRef,
    credential: GitCredential | None,
    limits: WorkspaceLimits,
    label: str,
) -> dict[str, Any]:
    """Provision against a (possibly remote) repo and report what happened. Cleans up."""
    manager = WorkspaceManager(limits)
    started = time.time()
    ws = manager.provision(pr, credential=credential)
    elapsed = round(time.time() - started, 2)

    report: dict[str, Any] = {
        "label": label,
        "clone_url": pr.clone_url,
        "pr_number": pr.pr_number,
        "fetch_ref": pr.fetch_ref,
        "requested_head": pr.head_sha,
        "base_sha": pr.base_sha,
        "auth": credential.username if credential else "anonymous",
        "elapsed_seconds": elapsed,
        "degraded": ws.degraded,
        "degraded_reason": ws.degraded_reason,
    }
    if ws.degraded:
        return report

    report["facts"] = _collect_clone_facts(manager, ws)
    report["base_present"] = (
        manager._has_commit(pr.base_sha, ws.checkout, ws.git_env) if pr.base_sha else None
    )
    report["head_matches_request"] = report["facts"]["head_checked_out"].startswith(
        pr.head_sha[:12]
    )
    report["checks"] = _security_checks(manager, ws, credential)

    root_before = ws.root
    manager.cleanup(ws)
    report["checks"].append(
        {"check": "cleanup removes the workspace", "pass": not root_before.exists(), "detail": ""}
    )
    report["all_passed"] = bool(report.get("head_matches_request")) and all(
        c["pass"] for c in report["checks"]
    )
    return report


def _ls_remote_sha(url: str, ref: str) -> str | None:
    result = subprocess.run(
        ["git", *GIT_SAFETY_CONFIG, "ls-remote", url, ref],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_TERMINAL_PROMPT": "0"},
    )
    line = result.stdout.strip().splitlines()
    return line[0].split("\t")[0] if line else None


def _render_provision_report(reports: list[dict[str, Any]]) -> str:
    lines = [
        "# Mergebot Workspace Manager — Real Provision Demos",
        "",
        f"prototype_version: `{PROTOTYPE_VERSION}`",
        "",
        "Each scenario provisions a real workspace (clone @ head SHA, base guarantee,",
        "split-jail credentials), asserts the security properties, then cleans up.",
        "",
    ]
    for report in reports:
        lines.append(f"## {report['label']}")
        lines.append("")
        lines.append("```json")
        meta = {k: v for k, v in report.items() if k not in {"checks", "facts"}}
        lines.append(json.dumps(meta, indent=2, sort_keys=True))
        lines.append("```")
        if report.get("facts"):
            lines.append("")
            lines.append("### clone facts")
            for key, value in report["facts"].items():
                lines.append(f"- {key}: `{value}`")
        if report.get("checks"):
            lines.append("")
            lines.append("| Security check | Result | Detail |")
            lines.append("|---|---|---|")
            for check in report["checks"]:
                mark = "✅" if check["pass"] else "❌"
                detail = (check.get("detail") or "").replace("|", "\\|")
                lines.append(f"| {check['check']} | {mark} | {detail} |")
        lines.append("")
    return "\n".join(lines)


def run_demo_suite(output: Path | None) -> int:
    """Run the real-world provision scenarios used as workspace-manager demos."""
    root = DEFAULT_ROOT_DIR / "demo"
    mergebot_url = "https://github.com/thehapyone/Mergebot.git"
    markupsafe_url = "https://github.com/pallets/markupsafe.git"
    reports: list[dict[str, Any]] = []

    # Real PR scenarios (public repos, no token needed) — resolve SHAs via ls-remote.
    for url, pr_number, base_ref, label in [
        (mergebot_url, 74, "refs/heads/main", "Mergebot PR #74 (feature PR, GitHub PR ref)"),
        (mergebot_url, 90, "refs/heads/main", "Mergebot PR #90 (dependency PR, GitHub PR ref)"),
    ]:
        fetch_ref = f"refs/pull/{pr_number}/head"
        head = _ls_remote_sha(url, fetch_ref)
        base = _ls_remote_sha(url, base_ref)
        if not head or not base:
            reports.append(
                {"label": label, "degraded": True, "degraded_reason": "ls-remote failed"}
            )
            continue
        reports.append(
            provision_report(
                PrRef(
                    clone_url=url,
                    head_sha=head,
                    base_sha=base,
                    pr_number=pr_number,
                    fetch_ref=fetch_ref,
                ),
                credential=None,
                limits=WorkspaceLimits(root_dir=root, depth=50, max_repo_mb=100_000),
                label=label,
            )
        )

    # markupsafe @ main with an older base, to exercise the base-SHA guarantee on depth=1.
    ms_head = _ls_remote_sha(markupsafe_url, "refs/heads/main") or _ls_remote_sha(
        markupsafe_url, "refs/heads/stable"
    )
    ms_base = _ls_remote_sha(markupsafe_url, "refs/tags/3.0.0") or ms_head
    if ms_head:
        reports.append(
            provision_report(
                PrRef(clone_url=markupsafe_url, head_sha=ms_head, base_sha=ms_base),
                credential=None,
                limits=WorkspaceLimits(root_dir=root, depth=1, max_repo_mb=100_000),
                label="MarkupSafe @ main, depth=1 (base-SHA guarantee via extra fetch)",
            )
        )

    # Degraded scenarios — must never raise.
    reports.append(
        provision_report(
            PrRef(
                clone_url="https://github.com/thehapyone/this-repo-does-not-exist.git",
                head_sha="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            ),
            credential=None,
            limits=WorkspaceLimits(root_dir=root, max_repo_mb=100_000),
            label="Degraded: nonexistent remote (graceful, no raise)",
        )
    )
    reports.append(
        provision_report(
            PrRef(clone_url=mergebot_url, head_sha="x", repo_size_kb=5_000_000),
            credential=None,
            limits=WorkspaceLimits(root_dir=root, max_repo_mb=1024),
            label="Degraded: repo exceeds max_repo_mb preflight (no clone attempted)",
        )
    )
    reports.append(
        provision_report(
            PrRef(clone_url=mergebot_url, head_sha="x"),
            credential=None,
            limits=WorkspaceLimits(root_dir=root, max_repo_mb=10**12),
            label="Degraded: insufficient disk for this clone (no clone attempted)",
        )
    )

    rendered = _render_provision_report(reports)
    if output:
        output.write_text(rendered, encoding="utf-8")
    print(rendered)
    non_degraded = [r for r in reports if not r.get("degraded")]
    expected_degraded = [
        r for r in reports if "Degraded:" in r["label"] or "nonexistent" in r["label"]
    ]
    ok = all(r.get("all_passed") for r in non_degraded) and all(
        r.get("degraded") for r in expected_degraded
    )
    return 0 if ok else 1


def self_test(source_repo: Path, head_sha: str, base_sha: str, token: str) -> dict[str, Any]:
    """Provision against a local repo and assert the security properties hold (offline)."""
    manager = WorkspaceManager(
        WorkspaceLimits(root_dir=DEFAULT_ROOT_DIR / "selftest", max_repo_mb=100_000)
    )
    credential = credential_from_runtime("github", token)
    pr = PrRef(
        clone_url=f"file://{source_repo.resolve()}",
        head_sha=head_sha,
        base_sha=base_sha,
        pr_number=0,
    )
    ws = manager.provision(pr, credential=credential)
    report: dict[str, Any] = {"degraded": ws.degraded, "degraded_reason": ws.degraded_reason}
    checks: list[dict[str, Any]] = [
        {
            "check": "clone succeeded (not degraded)",
            "pass": not ws.degraded,
            "detail": ws.degraded_reason or "",
        }
    ]
    if ws.degraded:
        report["checks"] = checks
        report["all_passed"] = False
        return report

    head_real = manager._git(
        ["rev-parse", "HEAD"], env=ws.git_env, cwd=ws.checkout, what="rev-parse", check=False
    ).stdout.strip()
    checks.append(
        {
            "check": "HEAD checked out at requested SHA",
            "pass": head_real.startswith(head_sha[:7]),
            "detail": head_real,
        }
    )
    base_ok = manager._has_commit(base_sha, ws.checkout, ws.git_env)
    checks.append({"check": "base commit present in history", "pass": base_ok, "detail": ""})
    checks.extend(_security_checks(manager, ws, credential))

    root_before = ws.root
    manager.cleanup(ws)
    checks.append(
        {"check": "cleanup removes the workspace", "pass": not root_before.exists(), "detail": ""}
    )

    bad = manager.provision(PrRef(clone_url="file:///nonexistent/repo.git", head_sha="deadbeef"))
    checks.append(
        {
            "check": "bogus clone degrades gracefully (no raise)",
            "pass": bad.degraded,
            "detail": bad.degraded_reason or "",
        }
    )
    report["checks"] = checks
    report["all_passed"] = all(c["pass"] for c in checks)
    return report


def _render_report(report: dict[str, Any]) -> str:
    lines = [
        "# Mergebot Workspace Manager — Prototype Self-Test (offline)",
        "",
        f"prototype_version: `{PROTOTYPE_VERSION}`",
        f"all_passed: **{report.get('all_passed')}**",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    for check in report.get("checks", []):
        mark = "✅" if check["pass"] else "❌"
        detail = check["detail"].replace("|", "\\|") if check.get("detail") else ""
        lines.append(f"| {check['check']} | {mark} | {detail} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Workspace manager prototype tests.")
    parser.add_argument(
        "--mode",
        choices=["selftest", "demo"],
        default="selftest",
        help="selftest = offline local clone; demo = real remote PR provisioning.",
    )
    parser.add_argument("--source", default=".", help="[selftest] Local repo to clone.")
    parser.add_argument("--head", help="[selftest] Head SHA to check out.")
    parser.add_argument("--base", help="[selftest] Base SHA to guarantee is present.")
    parser.add_argument("--token", default="prototype-secret-token-DO-NOT-LOG")
    parser.add_argument("--output", help="Write the rendered report here.")
    args = parser.parse_args(argv)

    if args.mode == "demo":
        return run_demo_suite(Path(args.output) if args.output else None)

    if not args.head or not args.base:
        parser.error("--head and --base are required for selftest mode")
    report = self_test(
        source_repo=Path(args.source), head_sha=args.head, base_sha=args.base, token=args.token
    )
    rendered = _render_report(report)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if report.get("all_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
