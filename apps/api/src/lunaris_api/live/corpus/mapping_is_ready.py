from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot
from lunaris_live.graph import ConceptGraph


def mapping_is_ready(graph: ConceptGraph, snapshot: CorpusSnapshot) -> bool:
    """Readiness binds the reports and actual attached materials to the same source and run."""
    reports = (graph.grounding_report, graph.mapping_report)
    if not graph.is_acyclic or any(
        report is None
        or report.status != "passed"
        or report.issues
        or report.source_digest != snapshot.source.digest
        or report.run_id != snapshot.source.run_id
        for report in reports
    ):
        return False
    return _coverage_matches(graph) and _assets_match(graph, snapshot)


def _coverage_matches(graph: ConceptGraph) -> bool:
    assert graph.grounding_report is not None
    decisions = graph.grounding_report.nodes
    if (
        len(decisions) != len(graph.nodes)
        or len({n.id for n in graph.nodes}) != len(graph.nodes)
        or {n.node_id for n in decisions} != {n.id for n in graph.nodes}
        or graph.grounding_report.uncovered_locators
        or graph.grounding_report.omitted_locators
    ):
        return False
    if any(
        n.classification == "unsupported"
        or (n.classification == "source" and not n.locators)
        or (n.classification == "prerequisite" and not n.rationale.strip())
        for n in decisions
    ):
        return False
    source_nodes = {n.node_id for n in decisions if n.classification == "source"}
    supported = {
        node.id
        for node in graph.nodes
        if any(asset.kind in ("lesson", "video_clip") for asset in node.assets)
    }
    return bool(source_nodes) and source_nodes <= supported


def _assets_match(graph: ConceptGraph, snapshot: CorpusSnapshot) -> bool:
    assert graph.mapping_report is not None
    approved = {
        (m.node_id, m.locator) for m in graph.mapping_report.mappings if m.status == "approved"
    }
    attached = {(node.id, asset.locator) for node in graph.nodes for asset in node.assets}
    return approved == attached and all(
        asset.verification is not None
        and asset.source_digest == snapshot.source.digest
        and asset.verification.source_digest == snapshot.source.digest
        and asset.verification.run_id == snapshot.source.run_id
        and asset.verification.verifier_version == graph.mapping_report.verifier_version
        for node in graph.nodes
        for asset in node.assets
    )
