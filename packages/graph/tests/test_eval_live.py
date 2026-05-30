"""Live golden-graph eval (build-spec §10 + Phase 0 §11 — the Failure-A eval).

Excluded from the default test run (marked ``eval``). Run with a real key:

    uv run --env-file .env pytest -m eval -q

Asserts the live builder preserves every golden prerequisite ordering and that its
own topological order is internally valid.
"""

import os

import pytest
from lunaris_graph.builder import PrerequisiteGraphBuilder
from lunaris_graph.judges import ClaudePrereqJudge
from lunaris_runtime.schema import Edge

from .golden import ALL_DOMAINS

pytestmark = pytest.mark.eval

_HAS_KEY = bool(os.getenv("ANTHROPIC_API_KEY"))
_MODEL = os.getenv("LUNARIS_MODEL_WORKER", "claude-haiku-4-5-20251001")


def _reachable(src: str, dst: str, edges: list[Edge]) -> bool:
    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(e.from_, []).append(e.to)
    stack, seen = list(adj.get(src, [])), set()
    while stack:
        node = stack.pop()
        if node == dst:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adj.get(node, []))
    return False


@pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set")
@pytest.mark.parametrize("domain", ALL_DOMAINS, ids=lambda d: d.name)
async def test_live_builder_preserves_golden_ordering(domain) -> None:
    # Arrange
    builder = PrerequisiteGraphBuilder(ClaudePrereqJudge(_MODEL))

    # Act
    graph = await builder.build(domain.kcs, frontier=[], goal=domain.goal)

    # Assert — internally valid order
    assert graph.is_acyclic
    pos = {kc_id: i for i, kc_id in enumerate(graph.topo_order)}
    for e in graph.edges:
        assert pos[e.from_] < pos[e.to]

    # Assert — every golden prerequisite is still enforced (reachability is robust to
    # transitive-reduction differences between the model's graph and the golden one)
    missing = [
        (a, b) for a, b in domain.edges if not (_reachable(a, b, graph.edges) and pos[a] < pos[b])
    ]
    assert not missing, f"golden orderings not preserved: {missing}"
