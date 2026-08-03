"""Cross-package contracts for the concept graph — every dependency on Live's graph goes through
one of these, never through a concrete implementation."""

from .graph_compiler import IGraphCompiler
from .graph_store import IGraphStore

__all__ = ["IGraphCompiler", "IGraphStore"]
