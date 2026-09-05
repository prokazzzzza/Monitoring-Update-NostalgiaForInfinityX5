import logging

logger = logging.getLogger("monitoring")


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO)
    # These libraries can include token-bearing request URLs in diagnostics.
    for name in ("httpx", "httpcore", "telegram"):
        dependency_logger = logging.getLogger(name)
        dependency_logger.handlers = [logging.NullHandler()]
        dependency_logger.propagate = False
