"""Shared fixtures: a scratch git repo and a provisioned split-jail workspace."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from mergebot.workspace.manager import (
    PrRef,
    Workspace,
    WorkspaceLimits,
    WorkspaceManager,
    credential_from_runtime,
)

FAKE_TOKEN = "test-secret-token-DO-NOT-LOG"


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@dataclass
class ScratchRepo:
    path: Path
    base_sha: str
    head_sha: str


@pytest.fixture
def scratch_repo(tmp_path: Path) -> ScratchRepo:
    """A repo with a base commit and a head commit touching source, tests, and manifests."""
    repo = tmp_path / "scratch-repo"
    repo.mkdir()
    run_git(repo, "init", "-b", "main")

    (repo / "app").mkdir()
    (repo / "app" / "service.py").write_text(
        "def fetch_user(user_id):\n"
        '    """Fetch a user."""\n'
        "    return {'id': user_id}\n"
        "\n"
        "def unrelated_helper():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_service.py").write_text(
        "from app.service import fetch_user\n"
        "\n"
        "def test_fetch_user():\n"
        "    assert fetch_user(1)['id'] == 1\n"
        "\n"
        "def test_obsolete():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    (repo / "pyproject.toml").write_text('[project]\nname = "scratch"\nversion = "1.0"\n')
    (repo / "poetry.lock").write_text("# lock v1\n")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "base")
    base_sha = run_git(repo, "rev-parse", "HEAD")

    (repo / "app" / "service.py").write_text(
        "def fetch_user(user_id):\n"
        '    """Fetch a user with validation."""\n'
        "    if user_id is None:\n"
        "        raise ValueError('user_id required')\n"
        "    return {'id': user_id}\n"
        "\n"
        "def unrelated_helper():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    # Deletion-only change in a test file (test_obsolete removed).
    (repo / "tests" / "test_service.py").write_text(
        "from app.service import fetch_user\n"
        "\n"
        "def test_fetch_user():\n"
        "    assert fetch_user(1)['id'] == 1\n",
        encoding="utf-8",
    )
    (repo / "pyproject.toml").write_text('[project]\nname = "scratch"\nversion = "2.0"\n')
    (repo / "poetry.lock").write_text("# lock v2\n")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "head")
    head_sha = run_git(repo, "rev-parse", "HEAD")

    return ScratchRepo(path=repo, base_sha=base_sha, head_sha=head_sha)


@pytest.fixture
def workspace_manager(tmp_path: Path) -> WorkspaceManager:
    return WorkspaceManager(WorkspaceLimits(root_dir=tmp_path / "workspaces", max_repo_mb=100_000))


@pytest.fixture
async def provisioned_workspace(
    scratch_repo: ScratchRepo, workspace_manager: WorkspaceManager
) -> Workspace:
    """A real (file:// cloned) workspace with a fake token in the git env."""
    pr = PrRef(
        clone_url=f"file://{scratch_repo.path.resolve()}",
        head_sha=scratch_repo.head_sha,
        base_sha=scratch_repo.base_sha,
        pr_number=7,
    )
    credential = credential_from_runtime("github", FAKE_TOKEN)
    workspace = await workspace_manager.provision(pr, credential=credential)
    yield workspace
    await workspace_manager.cleanup(workspace)
