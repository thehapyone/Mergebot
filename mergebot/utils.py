from mergebot.validator.config import load_config


def get_platform_type():
    """
    Returns the repository platform type from the validated config.
    """
    config = load_config()
    return config.repository.type
