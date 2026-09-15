import hashlib
import json

from lunaris_live.corpus.schemas.citation import CorpusCitation
from lunaris_live.corpus.schemas.claim import CorpusClaim
from lunaris_live.corpus.schemas.provenance import CorpusProvenance
from lunaris_live.corpus.schemas.section import CorpusSection
from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot
from lunaris_runtime.schema import Course, Module
from lunaris_runtime.schema.enums import ReviewGateStatus
from lunaris_runtime.schema.instruction import Item, Lesson
from pydantic import ValidationError


def _locator(module_id: str, kind: str, item_id: str) -> str:
    coordinates = json.dumps([module_id, kind, item_id], ensure_ascii=False)
    return kind + ":" + hashlib.sha256(coordinates.encode()).hexdigest()


def _lesson_section(module: Module, lesson: Lesson) -> CorpusSection | None:
    segments = [
        getattr(lesson.segments, phase)
        for phase in ("activate", "demonstrate", "apply", "integrate")
    ]
    prose = [segment.prose.strip() for segment in segments if segment.prose.strip()]
    if not prose:
        return None
    claims = tuple(
        CorpusClaim(
            text=claim.text, citation_id=claim.supported_by, status=claim.verifier_status.value
        )
        for segment in segments
        for claim in segment.claims
    )
    return CorpusSection(
        locator=_locator(module.id, "lesson", lesson.id),
        text="\n\n".join([module.title, *prose]),
        kind="lesson",
        objectives=tuple(objective.statement for objective in module.objectives),
        claims=claims,
    )


def _assessment_section(module: Module, item: Item) -> CorpusSection | None:
    if not item.prompt.strip():
        return None
    return CorpusSection(
        locator=_locator(module.id, "assessment", item.id),
        text="\n\n".join(part for part in [item.prompt, item.pass_criterion] if part),
        kind="assessment",
        answer_key=item.answer,
        objectives=(item.objective,)
        if item.objective
        else tuple(objective.statement for objective in module.objectives),
    )


def _sections(module: Module) -> tuple[CorpusSection, ...]:
    lessons = (_lesson_section(module, lesson) for lesson in module.lessons)
    assessments = (_assessment_section(module, item) for item in module.assessment.items)
    return tuple(section for section in (*lessons, *assessments) if section is not None)


def _caveats(course: Course) -> tuple[str, ...]:
    scope = [course.scope_note] if course.scope_note else []
    review = [
        gate.detail or gate.label
        for gate in course.review_gates
        if gate.status != ReviewGateStatus.PASSED
    ]
    return tuple(dict.fromkeys([*scope, *review]))


def _digest(snapshot: CorpusSnapshot) -> str:
    content = snapshot.model_dump(mode="json", exclude={"source"})
    content["title"] = snapshot.source.title
    content["adapter_version"] = snapshot.source.adapter_version
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _snapshot(course: Course, run_id: str) -> CorpusSnapshot:
    sections = tuple(section for module in course.modules for section in _sections(module))
    if not any(section.kind == "lesson" for section in sections):
        raise ValueError("Course has no usable lessons")
    return CorpusSnapshot(
        source=CorpusProvenance(
            course_id=course.id, title=course.topic, digest="0" * 64, run_id=run_id
        ),
        sections=sections,
        caveats=_caveats(course),
        citations=tuple(CorpusCitation.model_validate(c.model_dump()) for c in course.provenance),
    )


def normalize_course(course: Course, *, run_id: str) -> CorpusSnapshot:
    """Select public content as untrusted data; never copy learner, planner or budget state."""
    try:
        snapshot = _snapshot(course, run_id)
    except ValidationError as exc:
        raise ValueError("Course material exceeds source limits or has invalid references") from exc
    return snapshot.model_copy(
        update={"source": snapshot.source.model_copy(update={"digest": _digest(snapshot)})}
    )
