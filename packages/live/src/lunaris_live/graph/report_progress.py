import structlog

from .protocols import ICompileProgressSink
from .schema import CompilePhase, CompileProgress

logger = structlog.get_logger()


def report_progress(
    sink: ICompileProgressSink | None,
    phase: CompilePhase,
    *,
    done: int = 0,
    total: int = 0,
) -> None:
    """Report one beat of a compile, if anyone is listening, without ever costing the compile.

    A sink is a client's connection by another name, and clients disappear mid-compile — a learner
    closes the tab, a proxy times the stream out. Letting that propagate would trade a three-minute
    map for a lost progress bar, so a failing sink is logged and the compile carries on.

    Internal to the graph package: compilers report, nothing else does.
    """
    if sink is None:
        return
    try:
        sink(CompileProgress(phase=phase, done=done, total=total))
    except Exception:
        # Debug, not warning: a disconnected client is ordinary, and a compile of twenty concepts
        # would otherwise log twenty warnings for one learner closing a tab.
        logger.debug("live.graph.progress_sink_failed", phase=phase.value, exc_info=True)
