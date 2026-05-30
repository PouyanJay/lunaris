"""Lunaris prerequisite-graph builder — the correctness moat (Failure A).

The LLM makes only local pairwise judgments ("is A a prerequisite of B?");
deterministic code guarantees the structure (cycle-freedom, minimality, the
frontier→goal subgraph, and a valid topological order).
"""

from lunaris_graph.assembler import GraphAssembler
from lunaris_graph.builder import PrerequisiteGraphBuilder
from lunaris_graph.judges import ClaudePrereqJudge, StubPrereqJudge
from lunaris_graph.protocols import IPrereqJudge
from lunaris_graph.verdict import PrereqVerdict

__all__ = [
    "ClaudePrereqJudge",
    "GraphAssembler",
    "IPrereqJudge",
    "PrereqVerdict",
    "PrerequisiteGraphBuilder",
    "StubPrereqJudge",
]
