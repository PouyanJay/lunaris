import structlog


def bind_run_id(run_id: str, **extra: str) -> None:
    """Bind a correlation id (and optional extras) to the current async context.

    Every downstream log line picks these up automatically via contextvars.
    """
    structlog.contextvars.bind_contextvars(run_id=run_id, **extra)


def bind_request_id(request_id: str, **extra: str) -> None:
    """Bind a per-request correlation id (for non-build requests that aren't a ``run``, e.g. a
    delete). Same contextvars mechanism as ``bind_run_id`` so every downstream log line carries it.
    """
    structlog.contextvars.bind_contextvars(request_id=request_id, **extra)


def clear_correlation() -> None:
    structlog.contextvars.clear_contextvars()
