"""Directed-acyclic-graph algebra over plain ``(source, target)`` edges.

Both products build a prerequisite graph and both need the same guarantees from it — no cycles, a
valid teaching order, no redundant edges. The reasoning about *which* concept depends on which is
each product's own (Studio judges pairs with an LLM; Live's compiler emits dependencies directly),
but the structural guarantees are one implementation, here, so a fix reaches both.

Deliberately schema-free: edges are ``(source, target)`` pairs and are addressed by **index**, so
neither product's node or edge model leaks into the other's. Callers map the returned indices back
to their own edge objects.
"""

from .find_cycle import find_cycle
from .is_reachable import is_reachable
from .remove_cycles import remove_cycles
from .topological_order import topological_order

__all__ = ["find_cycle", "is_reachable", "remove_cycles", "topological_order"]
