"""Source-backed work always rechecks the current owned published Studio material."""

import pytest
from lunaris_api.live.corpus.access_guard import StudioCorpusAccessGuard
from lunaris_api.live.corpus.models.access_policy import CorpusAccessPolicy
from lunaris_api.live.corpus.normalize_course import normalize_course
from lunaris_api.live.corpus.unavailable import CorpusUnavailableError
from lunaris_api.live.work_refused import LiveWorkRefusedError
from lunaris_live.corpus.schemas.asset import NodeAsset
from lunaris_live.corpus.schemas.asset_verification import AssetVerification
from lunaris_live.graph import ConceptGraph, ConceptNode
from lunaris_live.graph.assembly import assemble
from lunaris_runtime.schema import Course
from test_studio_corpus_resolver import course_payload


class Courses:
    def __init__(self) -> None:
        self.course: Course | None = Course.model_validate(course_payload())
        self.calls: list[tuple[str, str | None]] = []

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        self.calls.append((course_id, owner_id))
        if self.course is None or owner_id != "owner":
            raise FileNotFoundError
        return self.course


def source_graph(courses: Courses) -> ConceptGraph:
    assert courses.course is not None
    source = normalize_course(courses.course, run_id="seed").source.model_copy(
        update={"status": "verified"}
    )
    asset = NodeAsset(
        asset_id="source-lesson",
        kind="lesson",
        origin="ingested",
        locator="lesson:source",
        source_digest=source.digest,
        excerpt="Consent",
        verification=AssetVerification(
            source_digest=source.digest, run_id=source.run_id, verifier_version="fixture"
        ),
    )
    graph = ConceptGraph(
        graph_id="graph",
        topic="Fixture",
        corpus=source,
        nodes=[ConceptNode(id="node", name="Consent", definition="Consent", assets=[asset])],
    )
    return with_verified_reports(graph)


def with_verified_reports(graph: ConceptGraph) -> ConceptGraph:
    assert graph.corpus is not None
    common = {"sourceDigest": graph.corpus.digest, "runId": graph.corpus.run_id, "status": "passed"}
    payload = graph.model_dump(by_alias=True)
    payload["groundingReport"] = {
        **common,
        "nodes": [
            {
                "nodeId": node.id,
                "classification": "source",
                "locators": [a.locator for a in node.assets],
            }
            for node in graph.nodes
        ],
    }
    payload["mappingReport"] = {
        **common,
        "mapperVersion": "fixture",
        "verifierVersion": "fixture",
        "mappings": [
            {
                "nodeId": node.id,
                "locator": asset.locator,
                "status": "approved",
                "reason": "verified",
                "evidence": ["Consent"],
            }
            for node in graph.nodes
            for asset in node.assets
        ],
    }
    return assemble(ConceptGraph.model_validate(payload))


async def test_current_source_checks_do_not_rebind_original_identity() -> None:
    courses = Courses()
    graph = source_graph(courses)
    before = graph.model_dump_json()
    await StudioCorpusAccessGuard(courses).check(graph, owner_id="owner", run_id="read")
    assert courses.calls == [("course-1", "owner")]
    assert graph.model_dump_json() == before


@pytest.mark.parametrize(
    "variant,expected",
    [
        ("deleted", 404),
        ("foreign", 404),
        ("unpublished", 404),
        ("changed", 409),
        ("wrong_id", 404),
        ("unverified", 409),
    ],
)
async def test_source_revocation_and_revision_fail_closed(variant: str, expected: int) -> None:
    courses = Courses()
    graph = source_graph(courses)
    owner = "owner"
    assert courses.course is not None
    if variant == "deleted":
        courses.course = None
    elif variant == "foreign":
        owner = "foreign"
    elif variant == "unpublished":
        courses.course = courses.course.model_copy(update={"status": "review"})
    elif variant == "changed":
        courses.course.modules[0].lessons[0].segments.activate.prose = "Changed lesson"
    elif variant == "wrong_id":
        courses.course = courses.course.model_copy(update={"id": "other"})
    else:
        graph = graph.model_copy(
            update={"corpus": graph.corpus.model_copy(update={"status": "pending"})}
        )
    with pytest.raises(LiveWorkRefusedError) as refused:
        await StudioCorpusAccessGuard(courses).check(graph, owner_id=owner, run_id="read")
    assert refused.value.status_code == expected


async def test_inspection_allows_pending_but_still_rechecks_source() -> None:
    courses = Courses()
    graph = source_graph(courses)
    graph = graph.model_copy(
        update={"corpus": graph.corpus.model_copy(update={"status": "pending"})}
    )
    guard = StudioCorpusAccessGuard(courses)
    await guard.check(graph, owner_id="owner", run_id="inspect", policy=CorpusAccessPolicy.INSPECT)
    courses.course = None
    with pytest.raises(CorpusUnavailableError):
        await guard.check(
            graph, owner_id="owner", run_id="inspect", policy=CorpusAccessPolicy.INSPECT
        )


@pytest.mark.parametrize(
    "variant",
    [
        "missing_report",
        "failed_report",
        "wrong_run",
        "missing_asset",
        "reported_gap",
        "duplicate_coverage",
    ],
)
async def test_verified_label_does_not_override_missing_or_invalid_evidence(variant: str) -> None:
    courses = Courses()
    graph = source_graph(courses)
    if variant == "missing_report":
        graph.mapping_report = None
    elif variant == "failed_report":
        graph.grounding_report = graph.grounding_report.model_copy(update={"status": "failed"})
    elif variant == "wrong_run":
        graph.mapping_report = graph.mapping_report.model_copy(update={"run_id": "different"})
    elif variant == "reported_gap":
        graph.grounding_report = graph.grounding_report.model_copy(
            update={"uncovered_locators": ("lesson:missing",)}
        )
    elif variant == "duplicate_coverage":
        graph.grounding_report = graph.grounding_report.model_copy(
            update={"nodes": graph.grounding_report.nodes * 2}
        )
    else:
        graph.nodes[0].assets = []
    guard = StudioCorpusAccessGuard(courses)
    with pytest.raises(LiveWorkRefusedError) as refused:
        await guard.check(graph, owner_id="owner", run_id="read")
    assert refused.value.status_code == 409
    await guard.check(graph, owner_id="owner", run_id="inspect", policy=CorpusAccessPolicy.INSPECT)
