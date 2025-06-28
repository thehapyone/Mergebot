from mergebot.validator.config import get_runtime_config


def get_platform_type():
    """
    Returns the repository platform type from the validated config.
    """
    config = get_runtime_config(as_pydantic=True)
    return config.repository.type
