"""The session lookup stays synchronous while cold generation is queued outside the turn."""

from unittest.mock import Mock
from uuid import uuid4

from lunaris_live.graph import ConceptGraph, ConceptNode, MasteryCriterion
from lunaris_live.sims.runtime.materials import SimMaterials
from lunaris_live.sims.runtime.models.preparation import SimPreparation


async def test_cold_lookup_queues_only_the_requested_node_and_never_builds_inline():
    criterion = MasteryCriterion(kind="manipulate", statement="Observe doubling", needs_sim=True)
    node = ConceptNode(id="n", name="Doubling", definition="y=2x", mastery_criteria=[criterion])
    graph = ConceptGraph(graph_id="g", topic="Functions", nodes=[node], topo_order=["n"])
    owner = str(uuid4())
    assets, queue = Mock(), Mock()
    assets.find.return_value = []
    queue.enqueue.return_value = "queued"
    runtime = SimMaterials(assets, queue)
    registry = await runtime.load(graph, owner_id=owner)
    assert registry.app_for(node, criterion) is None
    queue.enqueue.assert_not_called()
    await runtime.prepare(SimPreparation(graph, "n", "s", owner))
    request = queue.enqueue.call_args.args[0]
    assert request.node == node and request.criterion == criterion
    assert queue.enqueue.call_args.kwargs == {"session_id": "s", "owner_id": owner}
    assert request.run_id


async def test_spoken_criteria_do_not_start_an_unneeded_build():
    node = ConceptNode(
        id="n",
        name="History",
        definition="A chronology",
        mastery_criteria=[MasteryCriterion(kind="explain", statement="Explain the sequence")],
    )
    graph = ConceptGraph(graph_id="g", topic="History", nodes=[node], topo_order=["n"])
    assets, queue = Mock(), Mock()
    runtime = SimMaterials(assets, queue)
    await runtime.prepare(SimPreparation(graph, "n", "s", str(uuid4())))
    queue.enqueue.assert_not_called()
