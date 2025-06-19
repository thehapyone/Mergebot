import os
from typing import Any, Union, Optional
from mergebot.validator.config import get_runtime_config


def get_platform_type():
    """
    Returns the repository platform type from the validated config.
    """
    config = get_runtime_config(as_pydantic=True)
    return config.repository.type


def get_from_dict_or_env(
    data: dict[str, Any],
    key: Union[str, list[str]],
    env_key: str,
    default: Optional[str] = None,
) -> str:
    """Get a value from a dictionary or an environment variable."""
    keys = key if isinstance(key, (list, tuple)) else [key]
    for k in keys:
        if k in data and data[k]:
            return data[k]

    return get_from_env(keys[0], env_key, default)


def get_from_env(key: str, env_key: str, default: Optional[str] = None) -> str:
    """Get a value from an environment variable or default.""" 
    if env_value := os.environ.get(env_key):
        return env_value
    if default is not None:
        return default

    raise ValueError(
        f"Did not find {key}, please add an environment variable `{env_key}` which "
        f"contains it, or pass `{key}` as a named parameter."
    )
