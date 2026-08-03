"""Cross-package contracts for the concept graph — every dependency on Live's graph goes through
one of these, never through a concrete implementation."""

from .compile_progress_sink import ICompileProgressSink
from .graph_compiler import IGraphCompiler
from .graph_store import IGraphStore

__all__ = ["ICompileProgressSink", "IGraphCompiler", "IGraphStore"]
