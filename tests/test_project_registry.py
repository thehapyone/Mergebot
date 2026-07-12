"""Per-project override merging: unset fields must fall back to the global config."""

from mergebot.project_registry import ProjectContext
from mergebot.validator.config import Config, ProjectDefinition


def make_base_config() -> Config:
    return Config(
        llm={"model": "gpt-test"},
        repository={
            "type": "github",
            "github": {"private_token": "test-token"},
            "projects": [{"path": "acme/one"}],
        },
        analysis={"max_mrs": 12, "draft_mrs": True},
        context={
            "workspace": {"clone_timeout": 300, "root_dir": "/data/workspaces"},
            "fact_pack": {"token_budget": 20_000},
        },
    )


def build_project_runtime(overrides: dict):
    base = make_base_config()
    definition = ProjectDefinition(path="acme/one", overrides=overrides)
    context = ProjectContext(project_path="acme/one", config=base, definition=definition)
    return context.build_runtime()


class TestContextOverrideMerge:
    def test_partial_override_keeps_global_siblings(self):
        """Overriding one context field must not reset its siblings to defaults."""
        runtime = build_project_runtime({"context": {"fact_pack": {"token_budget": 8_000}}})

        assert runtime.config.context.fact_pack.token_budget == 8_000
        # global values survive the merge instead of resetting to model defaults
        assert runtime.config.context.workspace.clone_timeout == 300
        assert runtime.config.context.workspace.root_dir == "/data/workspaces"

    def test_no_override_keeps_global_config(self):
        runtime = build_project_runtime({})
        assert runtime.config.context.workspace.clone_timeout == 300
        assert runtime.config.context.fact_pack.token_budget == 20_000

    def test_analysis_partial_override_keeps_global_siblings(self):
        runtime = build_project_runtime({"analysis": {"max_mrs": 5}})
        assert runtime.config.analysis.max_mrs == 5
        # global draft_mrs=True survives instead of resetting to the model default (False)
        assert runtime.config.analysis.draft_mrs is True
