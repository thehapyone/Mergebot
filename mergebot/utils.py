import os

from mergebot.validator.config import Config, load_config


def configure_telemetry(config: Config | None = None):
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

    if config is None:
        try:
            config = load_config()
        except SystemExit:
            # Configuration load failures already logged upstream.
            return

    telemetry_cfg = getattr(config, "telemetry", None)
    enabled = bool(getattr(telemetry_cfg, "enabled", False))

    if enabled:
        # Allow telemetry
        os.environ.pop("OTEL_SDK_DISABLED", None)
    else:
        # Disable all OpenTelemetry (CrewAI included)
        os.environ["OTEL_SDK_DISABLED"] = "true"
