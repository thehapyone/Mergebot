"""Workspace manager: split-jail security invariants, preflight guards, lifecycle.

Includes the mandatory credential deny-list checks (design doc §3.1): the git token
must be structurally unreachable from anything inside the checkout jail.
"""

import json
import shutil
import stat
import subprocess
import time
from collections import namedtuple
from pathlib import Path

import pytest

from mergebot.workspace.manager import (
    PathJailError,
    PrRef,
    WorkspaceLimits,
    WorkspaceManager,
    credential_from_runtime,
)
from tests.conftest import FAKE_TOKEN


def git_in_workspace(workspace, *args: str) -> str:
    """Run git in the checkout with the workspace's persisted (token-bearing) env."""
    result = subprocess.run(
        ["git", *args],
        cwd=workspace.checkout,
        env=workspace.git_env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def token_leak_scan(checkout: Path, token: str) -> list[str]:
    """Any file under the checkout (incl. .git) where the token appears."""
    hits = []
    for path in checkout.rglob("*"):
        if not path.is_file():
            continue
        try:
            if token in path.read_text(encoding="utf-8", errors="ignore"):
                hits.append(str(path.relative_to(checkout)))
        except OSError:
            continue
    return hits


class TestProvisionedWorkspace:
    async def test_head_and_base(self, provisioned_workspace, scratch_repo):
        assert not provisioned_workspace.degraded, provisioned_workspace.degraded_reason
        head = git_in_workspace(provisioned_workspace, "rev-parse", "HEAD").strip()
        assert head == scratch_repo.head_sha
        assert provisioned_workspace.base_present

    async def test_credential_deny_list(self, provisioned_workspace):
        """Mandatory §3.1 deny-list: the token is structurally outside the tool jail."""
        workspace = provisioned_workspace
        # secrets/ is outside the checkout jail
        assert not workspace.secrets_dir.resolve().is_relative_to(workspace.checkout.resolve())
        # token is nowhere on disk under the checkout, not even .git
        assert token_leak_scan(workspace.checkout, FAKE_TOKEN) == []
        # token is not cached in any git config
        config = git_in_workspace(workspace, "config", "--list", "--show-origin")
        assert FAKE_TOKEN not in config
        # askpass helper is secret-free and owner-only
        helper = workspace.secrets_dir / "askpass.sh"
        assert helper.exists()
        assert FAKE_TOKEN not in helper.read_text(encoding="utf-8")
        assert stat.S_IMODE(helper.stat().st_mode) == 0o700
        # the jail resolver refuses to reach the helper
        with pytest.raises(PathJailError):
            workspace.resolve_in_checkout("../secrets/askpass.sh")

    async def test_hooks_neutralized(self, provisioned_workspace):
        hooks = git_in_workspace(provisioned_workspace, "config", "--get", "core.hooksPath")
        assert hooks.strip() in {"", "/dev/null"}

    async def test_path_jail(self, provisioned_workspace):
        workspace = provisioned_workspace
        resolved = workspace.resolve_in_checkout("app/service.py")
        assert resolved.exists()
        for bad_path in ["../secrets/askpass.sh", "/etc/passwd", ".git/config", "../../.."]:
            with pytest.raises(PathJailError):
                workspace.resolve_in_checkout(bad_path)

    async def test_path_jail_rejects_symlink_escape(self, provisioned_workspace):
        workspace = provisioned_workspace
        evil = workspace.checkout / "evil-link"
        evil.symlink_to(workspace.secrets_dir)
        try:
            with pytest.raises(PathJailError):
                workspace.resolve_in_checkout("evil-link/askpass.sh")
        finally:
            evil.unlink()

    async def test_cleanup_removes_workspace(self, scratch_repo, workspace_manager):
        pr = PrRef(
            clone_url=f"file://{scratch_repo.path.resolve()}",
            head_sha=scratch_repo.head_sha,
            base_sha=scratch_repo.base_sha,
        )
        workspace = await workspace_manager.provision(
            pr, credential=credential_from_runtime("github", FAKE_TOKEN)
        )
        assert workspace.root.exists()
        await workspace_manager.cleanup(workspace)
        assert not workspace.root.exists()


class TestPreflight:
    async def test_oversized_repo_degrades(self, tmp_path, scratch_repo):
        manager = WorkspaceManager(WorkspaceLimits(root_dir=tmp_path / "ws", max_repo_mb=1024))
        pr = PrRef(
            clone_url=f"file://{scratch_repo.path.resolve()}",
            head_sha=scratch_repo.head_sha,
            repo_size_kb=5_000_000,
        )
        workspace = await manager.provision(pr)
        assert workspace.degraded
        assert "too large" in workspace.degraded_reason

    async def test_unwritable_root_degrades(self, tmp_path, monkeypatch):
        manager = WorkspaceManager(WorkspaceLimits(root_dir=tmp_path / "ws"))
        monkeypatch.setattr("mergebot.workspace.manager.os.access", lambda *_: False)
        workspace = await manager.provision(PrRef(clone_url="file:///x", head_sha="x"))
        assert workspace.degraded
        assert "not writable" in workspace.degraded_reason

    async def test_insufficient_disk_degrades(self, tmp_path, monkeypatch):
        manager = WorkspaceManager(WorkspaceLimits(root_dir=tmp_path / "ws", max_repo_mb=2048))
        usage = namedtuple("usage", "total used free")
        monkeypatch.setattr(
            "mergebot.workspace.manager.shutil.disk_usage",
            lambda _: usage(total=10**12, used=10**12, free=1024 * 1024),
        )
        workspace = await manager.provision(PrRef(clone_url="file:///x", head_sha="x"))
        assert workspace.degraded
        assert "insufficient disk" in workspace.degraded_reason

    async def test_bogus_clone_degrades_without_raising(self, tmp_path):
        manager = WorkspaceManager(WorkspaceLimits(root_dir=tmp_path / "ws", max_repo_mb=100_000))
        workspace = await manager.provision(
            PrRef(clone_url="file:///nonexistent/repo.git", head_sha="deadbeef")
        )
        assert workspace.degraded
        assert workspace.degraded_reason


class TestGitEnv:
    def test_network_env_passthrough(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.corp:3128")
        monkeypatch.setenv("NO_PROXY", ".corp.internal")
        monkeypatch.setenv("GIT_SSL_CAINFO", "/etc/ssl/corp-ca.pem")
        monkeypatch.setenv("SOME_UNRELATED_SECRET", "must-not-leak")
        manager = WorkspaceManager(WorkspaceLimits(root_dir=tmp_path / "ws"))
        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()

        env = manager._git_env(secrets_dir, credential_from_runtime("github", FAKE_TOKEN))

        assert env["HTTPS_PROXY"] == "http://proxy.corp:3128"
        assert env["NO_PROXY"] == ".corp.internal"
        assert env["GIT_SSL_CAINFO"] == "/etc/ssl/corp-ca.pem"
        assert "SOME_UNRELATED_SECRET" not in env  # allowlist, not a blanket copy


class TestSweeper:
    async def test_sweep_throttled_within_interval(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mergebot.workspace.manager.WorkspaceManager._last_sweep_at", None)
        manager = WorkspaceManager(WorkspaceLimits(root_dir=tmp_path / "ws"))
        await manager.sweep_orphans()
        # Second call inside the throttle window is a no-op even with sweepable dirs.
        stale = tmp_path / "ws" / "mergebot-pr9-stale"
        stale.mkdir()
        (stale / ".mergebot-workspace").write_text(json.dumps({"created_at": 0}))
        assert await manager.sweep_orphans() == []
        assert stale.exists()

    async def test_sweep_removes_only_expired_orphans(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mergebot.workspace.manager.WorkspaceManager._last_sweep_at", None)
        root = tmp_path / "ws"
        manager = WorkspaceManager(WorkspaceLimits(root_dir=root))

        def fake_workspace(name: str, created_at: int) -> Path:
            path = root / name
            path.mkdir()
            (path / ".mergebot-workspace").write_text(json.dumps({"created_at": created_at}))
            return path

        now = int(time.time())
        old = fake_workspace("mergebot-pr1-old", now - 8 * 60 * 60)
        fresh = fake_workspace("mergebot-pr2-fresh", now - 60)
        unrelated = root / "not-a-workspace"
        unrelated.mkdir()

        removed = await manager.sweep_orphans(ttl_seconds=6 * 60 * 60)

        assert [Path(item).name for item in removed] == [old.name]
        assert not old.exists()
        assert fresh.exists()
        assert unrelated.exists()
        shutil.rmtree(root)
