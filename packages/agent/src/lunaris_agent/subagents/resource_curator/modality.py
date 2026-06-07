from collections import Counter

from lunaris_runtime.schema import Modality, Module, PrerequisiteGraph


def representative_modality(module: Module, graph: PrerequisiteGraph | None) -> Modality | None:
    """The one modality that best characterizes a module's learning shape (CQ Phase 2).

    A module groups several KCs that may mix modalities; the query translator works
    per-competency, so it needs a single signal. Resolve it as the DOMINANT modality among the
    module's classified KCs (most common wins; ties broken deterministically by enum order).
    Returns ``None`` when there is no graph or none of the module's KCs were classified — the
    translator then shapes from the goal type alone, never from a guessed modality.
    """
    if graph is None:
        return None
    kc_ids = set(module.kcs)
    modalities = [
        node.modality for node in graph.nodes if node.id in kc_ids and node.modality is not None
    ]
    if not modalities:
        return None
    counts = Counter(modalities)
    order = list(Modality)
    # Iterate the distinct modalities (Counter keys): most common wins, ties → earliest enum member.
    return max(counts, key=lambda modality: (counts[modality], -order.index(modality)))
