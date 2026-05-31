import logging
import sys

import structlog

from .redaction import redact_sensitive


def configure_logging(*, level: str = "INFO", json_output: bool = True) -> None:
    """Configure structlog once at an application entry point.

    Never call this inside library code — libraries call ``structlog.get_logger()``
    and inherit whatever the host configured.
    """
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,  # run_id / request_id binding
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_sensitive,  # strip secrets/credentials before any sink — defense in depth
        structlog.processors.StackInfoRenderer(),
        structlog.processors.dict_tracebacks,
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )
    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=getattr(logging, level.upper())
    )
