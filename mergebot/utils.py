import os
from mergebot.validator.config import get_runtime_config


def get_platform_type():
    """
    Returns the repository platform type from the validated config.
    """
    config = get_runtime_config(as_pydantic=True)
    return config.repository.type


def configure_telemetry():
    """
    Configures OpenTelemetry enable/disable based on MergeBot runtime config
    and existing environment variables.

    Rules:
    1. If the user has explicitly set OTEL_SDK_DISABLED=true, respect it and keep
       telemetry disabled, regardless of the config file.
    2. Otherwise, read `telemetry.enabled` from the runtime config
       (defaults to False).
       • If enabled is True  -> remove OTEL_SDK_DISABLED so telemetry is allowed.
       • If enabled is False -> set OTEL_SDK_DISABLED=true to disable telemetry.
    """

    # Honour explicit user override
    if os.getenv("OTEL_SDK_DISABLED", "").lower() == "true":
        return

    cfg = get_runtime_config() or {}
    telemetry_cfg = cfg.get("telemetry", {}) if isinstance(cfg, dict) else {}
    enabled = telemetry_cfg.get("enabled", False)

    if enabled:
        # Allow telemetry
        os.environ.pop("OTEL_SDK_DISABLED", None)
    else:
        # Disable all OpenTelemetry (CrewAI included)
        os.environ["OTEL_SDK_DISABLED"] = "true"
