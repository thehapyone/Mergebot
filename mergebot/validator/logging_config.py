import logging

from rich.logging import RichHandler

logger = logging.getLogger("mergebot")
if not logger.hasHandlers():
    logger.setLevel(logging.INFO)
    handler = RichHandler(
        rich_tracebacks=True,
        show_time=True,
        show_level=True,
        show_path=True,
        markup=True,
    )
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
