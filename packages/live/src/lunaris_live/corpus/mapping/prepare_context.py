import json
from collections.abc import Iterator

from .models.candidate import MappingCandidate
from .models.context import MappingContext
from .models.request import MappingRequest
from .schemas.report import MappingGap

_CONTEXT_LIMIT = 64000
_CANDIDATE_LIMIT = 60


def prepare_mapping_context(request: MappingRequest) -> MappingContext:
    """Select bounded, answer-free source material; exclusions remain inspectable gaps."""
    source_nodes = _source_nodes(request)
    graph_data = [node.model_dump(mode="json", exclude={"assets"}) for node in request.graph.nodes]
    header = {
        "sourceDigest": request.snapshot.source.digest,
        "nodes": graph_data,
        "sourceNodeIds": sorted(source_nodes),
        "caveats": request.snapshot.caveats,
    }
    if len(json.dumps(header)) > 24000:
        raise ValueError("graph exceeds mapping context")
    candidates: list[MappingCandidate] = []
    data: list[dict[str, object]] = []
    gaps: list[MappingGap] = []
    for index, candidate in enumerate(_candidates(request)):
        if index >= 200:
            gaps.append(MappingGap(reason="candidate_limit"))
            break
        if len(candidates) >= _CANDIDATE_LIMIT:
            gaps.append(MappingGap(locator=candidate.locator, reason="candidate_limit"))
            break
        item = _public_candidate(candidate)
        if len(json.dumps({**header, "candidates": [*data, item]})) > _CONTEXT_LIMIT:
            gaps.append(MappingGap(locator=candidate.locator, reason="context_limit"))
            continue
        candidates.append(candidate)
        data.append(item)
    if request.inventory.gaps:
        gaps.append(MappingGap(reason="video_unavailable"))
    return MappingContext(
        tuple(candidates), json.dumps({**header, "candidates": data}), source_nodes, tuple(gaps)
    )


def _source_nodes(request: MappingRequest) -> frozenset[str]:
    graph, snapshot = request.graph, request.snapshot
    report, source = graph.grounding_report, graph.corpus
    if (
        source is None
        or source.status == "failed"
        or report is None
        or report.status != "passed"
        or source.digest != snapshot.source.digest
        or source.course_id != snapshot.source.course_id
        or report.source_digest != snapshot.source.digest
        or report.issues
        or report.uncovered_locators
        or report.omitted_locators
    ):
        raise ValueError("untrusted grounding identity")
    node_ids = {node.id for node in graph.nodes}
    reviewed = [node.node_id for node in report.nodes]
    available = {section.locator for section in snapshot.sections}
    if (
        len(node_ids) != len(graph.nodes)
        or len(set(reviewed)) != len(reviewed)
        or set(reviewed) != node_ids
    ):
        raise ValueError("grounding node coverage mismatch")
    for node in report.nodes:
        if node.classification == "unsupported" or (
            node.classification == "source"
            and (not node.locators or not set(node.locators) <= available)
        ):
            raise ValueError("unsupported source node")
    source_nodes = frozenset(
        node.node_id for node in report.nodes if node.classification == "source"
    )
    if not source_nodes:
        raise ValueError("no source-supported nodes")
    return source_nodes


def _candidates(request: MappingRequest) -> Iterator[MappingCandidate]:
    locators = [section.locator for section in request.snapshot.sections]
    locators.extend(clip.locator for clip in request.inventory.clips)
    if len(set(locators)) != len(locators):
        raise ValueError("candidate locator collision")
    for section in request.snapshot.sections:
        yield MappingCandidate(
            section.locator, section.kind, section.text, request.snapshot.source.title
        )
    for clip in request.inventory.clips:
        yield MappingCandidate(
            clip.locator,
            "video_clip",
            "\n".join(cue.text for cue in clip.transcript),
            clip.title,
            clip,
        )


def _public_candidate(candidate: MappingCandidate) -> dict[str, object]:
    return {
        "locator": candidate.locator,
        "kind": candidate.kind,
        "text": candidate.excerpt,
        "clip": candidate.clip.model_dump(mode="json") if candidate.clip else None,
    }
