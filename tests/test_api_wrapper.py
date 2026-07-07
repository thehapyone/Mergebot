"""Typed PrRef extraction from both platform wrappers, and the text-contract delegates."""

from types import SimpleNamespace
from typing import ClassVar

from mergebot.tools.api_base import PullRequestAPIBase, PullRequestDetails
from mergebot.tools.github.api_wrapper import GitHubAPIWrapper
from mergebot.tools.gitlab.api_wrapper import GitlabAPIWrapper
from mergebot.workspace.manager import PrRef


def make_github_wrapper() -> GitHubAPIWrapper:
    wrapper = GitHubAPIWrapper.model_construct(config=None, project_path="owner/repo")
    wrapper.github_repo_instance = SimpleNamespace(
        clone_url="https://github.com/owner/repo.git", size=345
    )
    return wrapper


def make_gitlab_wrapper() -> GitlabAPIWrapper:
    wrapper = GitlabAPIWrapper.model_construct(config=None, project_path="group/project")
    wrapper.gitlab_repo_instance = SimpleNamespace(
        http_url_to_repo="https://gitlab.example.com/group/project.git"
    )
    return wrapper


class TestGitHubPrRef:
    def test_build_pr_ref_fields(self):
        wrapper = make_github_wrapper()
        pr = SimpleNamespace(
            head=SimpleNamespace(sha="headsha"), base=SimpleNamespace(sha="basesha"), number=42
        )
        ref = wrapper._build_pr_ref(pr)
        assert ref == PrRef(
            clone_url="https://github.com/owner/repo.git",
            head_sha="headsha",
            base_sha="basesha",
            pr_number=42,
            fetch_ref="refs/pull/42/head",
            repo_size_kb=345,
        )

    def test_build_pr_ref_returns_none_on_failure(self):
        wrapper = make_github_wrapper()
        wrapper.github_repo_instance = None
        assert wrapper._build_pr_ref(SimpleNamespace()) is None

    def test_resolve_git_token_prefers_app_token(self):
        wrapper = make_github_wrapper()
        wrapper.github_app_access_token = "app-token"
        wrapper.github_personal_access_token = "pat-token"
        assert wrapper.resolve_git_token() == "app-token"
        wrapper.github_app_access_token = None
        assert wrapper.resolve_git_token() == "pat-token"

    def test_get_pull_request_delegates_to_text(self, monkeypatch):
        wrapper = make_github_wrapper()
        details = PullRequestDetails(details="pretty text", details_no_patch="no patch")
        monkeypatch.setattr(GitHubAPIWrapper, "get_pull_request_with_ref", lambda self, n: details)
        assert wrapper.get_pull_request(1) == "pretty text"

    def test_get_pull_request_preserves_error_dict(self, monkeypatch):
        wrapper = make_github_wrapper()
        error = {"error": "Failed to retrieve pull request details for ID 1: boom"}
        monkeypatch.setattr(GitHubAPIWrapper, "get_pull_request_with_ref", lambda self, n: error)
        assert wrapper.get_pull_request(1) is error


class TestGitLabPrRef:
    def test_build_pr_ref_fields(self, monkeypatch):
        wrapper = make_gitlab_wrapper()
        monkeypatch.setattr(wrapper, "_repo_size_kb", lambda: 678)
        mr = SimpleNamespace(sha="headsha", diff_refs={"base_sha": "basesha"}, iid=9)
        ref = wrapper._build_pr_ref(mr)
        assert ref == PrRef(
            clone_url="https://gitlab.example.com/group/project.git",
            head_sha="headsha",
            base_sha="basesha",
            pr_number=9,
            fetch_ref="refs/merge-requests/9/head",
            repo_size_kb=678,
        )

    def test_repo_size_none_when_statistics_unavailable(self):
        wrapper = make_gitlab_wrapper()
        wrapper.gitlab = SimpleNamespace(
            projects=SimpleNamespace(get=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("403")))
        )
        wrapper.gitlab_repository = "group/project"
        assert wrapper._repo_size_kb() is None
        mr = SimpleNamespace(sha="headsha", diff_refs=None, iid=9)
        ref = wrapper._build_pr_ref(mr)
        assert ref.repo_size_kb is None
        assert ref.base_sha is None  # missing diff_refs tolerated

    def test_resolve_git_token(self):
        wrapper = make_gitlab_wrapper()
        wrapper.gitlab_personal_access_token = "glpat"
        assert wrapper.resolve_git_token() == "glpat"


class TestPrettyPrintPatchToggle:
    PR_DETAILS: ClassVar[dict] = {
        "number": 1,
        "title": "t",
        "user": "u",
        "state": "open",
        "created_at": "2026-01-01",
        "updated_at": "2026-01-02",
        "base": "main",
        "head": "feature",
        "url": "https://example.com/pr/1",
        "body": "body",
        "file_changes": [
            {"filename": "a.py", "additions": 1, "deletions": 0, "patch": "SECRET_PATCH_BODY"}
        ],
    }

    def test_include_patch_default(self):
        text = PullRequestAPIBase.pretty_print_pull_request(self.PR_DETAILS)
        assert "SECRET_PATCH_BODY" in text

    def test_exclude_patch(self):
        text = PullRequestAPIBase.pretty_print_pull_request(self.PR_DETAILS, include_patch=False)
        assert "SECRET_PATCH_BODY" not in text
        assert "Repository Context compressed diff" in text
        # file metadata is still listed
        assert "File: a.py" in text
