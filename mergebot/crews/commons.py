import re
from collections.abc import Callable
from typing import Any

from crewai import LLM, Crew, Process
from crewai.events.types.llm_events import LLMCallType
from crewai.project import crew
from crewai.utilities.internal_instructor import InternalInstructor

from mergebot.validator.config import Config
from mergebot.validator.logging_config import logger


def extract_class_name(class_string: str) -> str:
    # Regular expression to find anything inside parentheses
    match = re.search(r"\((.*?)\)", class_string)
    return match.group(1) if match else class_string


class LiteLLMRoutedLLM(LLM):
    """LLM pinned to CrewAI's LiteLLM route for every provider string.

    CrewAI 1.14 routes model strings with native-provider prefixes (azure/,
    anthropic/, gemini/, ...) to per-provider SDK classes and raises ImportError
    when the matching extra is not installed — `is_litellm=True` does not bypass
    the probing, and whether a given string crashes depends on the model name
    appearing in CrewAI's constants. Mergebot's multi-provider support is the
    LiteLLM model-string surface (as on CrewAI 0.203), so native-provider probing
    is disabled and every model string keeps the LiteLLM code path.
    """

    @classmethod
    def _get_native_provider(cls, provider: str) -> type | None:
        return None

    def _structured_call_with_usage(
        self,
        params: dict[str, Any],
        from_task: Any,
        from_agent: Any,
        response_model: Any,
    ) -> str:
        """Structured-output call via instructor, with token accounting restored.

        Replicates the `response_model and is_litellm` branch of crewai 1.14's
        `_handle_non_streaming_response`, which discards the usage block returned
        by the API (it emits `usage=None`) — leaving `crew.usage_metrics` at zero
        for every structured call and silently blanking token analytics.
        Instructor attaches the raw completion to the parsed model, so the usage
        is recovered from there.
        """
        messages = params.get("messages", [])
        if not messages:
            raise ValueError("Messages are required when using response_model")

        combined_content = "\n\n".join(
            f"{msg['role'].upper()}: {msg['content']}" for msg in messages
        )
        instructor_instance = InternalInstructor(
            content=combined_content,
            model=response_model,
            llm=self,
        )
        result = instructor_instance.to_pydantic()

        usage = getattr(getattr(result, "_raw_response", None), "usage", None)
        usage_dict = usage.model_dump() if hasattr(usage, "model_dump") else None
        if usage_dict:
            self._track_token_usage_internal(usage_dict)
        else:
            logger.warning(
                "Structured LLM call returned no usage block; token analytics "
                "will under-count this call."
            )

        structured_response = result.model_dump_json()
        self._handle_emit_call_events(
            response=structured_response,
            call_type=LLMCallType.LLM_CALL,
            from_task=from_task,
            from_agent=from_agent,
            messages=params["messages"],
            usage=usage_dict,
        )
        return structured_response

    def _handle_non_streaming_response(
        self,
        params: dict[str, Any],
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: Any = None,
        from_agent: Any = None,
        response_model: Any = None,
    ) -> str | Any:
        if response_model and self.is_litellm:
            return self._structured_call_with_usage(params, from_task, from_agent, response_model)
        return super()._handle_non_streaming_response(
            params, callbacks, available_functions, from_task, from_agent, response_model
        )

    async def _ahandle_non_streaming_response(
        self,
        params: dict[str, Any],
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: Any = None,
        from_agent: Any = None,
        response_model: Any = None,
    ) -> str | Any:
        if response_model and self.is_litellm:
            # Upstream's async branch calls the same synchronous instructor path.
            return self._structured_call_with_usage(params, from_task, from_agent, response_model)
        return await super()._ahandle_non_streaming_response(
            params, callbacks, available_functions, from_task, from_agent, response_model
        )


class BotBaseCrew:
    """A base configuration for common crew definition"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"
    verbose: bool = False

    def __init__(
        self,
        config: Config,
        finding_file_checker: Callable[[str], bool] | None = None,
    ):
        self.config = config
        # Resolved at guardrail-execution time, so the file-existence check binds
        # to the review that is running even though crews are built before the
        # workspace exists.
        self.finding_file_checker = finding_file_checker
        # Get the LLM model for this crew
        crew_name = extract_class_name(self.__class__.__name__)
        llm_model = self.config.get_llm_model_for_crew(crew_name)
        self.llm = LiteLLMRoutedLLM(
            model=llm_model, drop_params=True, additional_drop_params=["stop"]
        )

    @crew
    def crew(self) -> Crew:
        """Creates the crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=self.verbose,
            output_log_file=True,
        )
