from pydantic import Field, field_validator

from .base import CourseModel
from .build_provenance import CapabilityBuildTag
from .course_scope import CourseScope
from .course_videos import CourseVideos
from .cover_artifact import CoverArtifact
from .enums import CourseStatus, GoalType
from .instruction import Module
from .knowledge import Citation, PrerequisiteGraph
from .learner import LearnerModel
from .review_gate import ReviewGate
from .settings import BudgetLedger, CourseSettings, RiskProfile

# Courses persisted before the coverage-gap disclosure moved off the top warning (PR #179) appended
# a competency sentence to scope_note, which the reader surfaced as an alarming amber banner. That
# disclosure now lives only in the scope band ("Does not fully build: …"); a course built before the
# move still carries the sentence at the tail of its stored scope_note. Strip it on read so every
# existing course reflects current behavior without a rebuild — the sentence was always appended
# last, so it runs from this marker to the end of the note. Idempotent: post-move notes lack it.
# A read-time shim, deletable once every pre-#179 row has been rebuilt or backfilled; until then it
# is the only thing that removes the sentence, since nothing recomputes scope_note on load.
_LEGACY_COVERAGE_GAP_MARKER = "It does not fully build some promised competencies:"


def _without_legacy_coverage_gap_sentence(scope_note: str) -> str:
    marker_at = scope_note.find(_LEGACY_COVERAGE_GAP_MARKER)
    if marker_at == -1:
        return scope_note
    return scope_note[:marker_at].rstrip()


class Course(CourseModel):
    """The single source of truth. Agents read slices they need, write the slice they own."""

    id: str
    topic: str  # the raw user query
    goal_concept: str = ""  # KnowledgeComponent id where the journey ends
    goal_type: GoalType = GoalType.KNOWLEDGE  # carried from the brief (CQ Phase 1.0)
    # An honest caveat when a research-needing goal could not be grounded in its real standard
    # (CQ Phase 1.6): empty when fully grounded or not research-needing; the reader shows it so a
    # generic course is never presented as an authoritative guide to the standard.
    scope_note: str = ""
    # The scope-realism band (CQ Phase 3.1): effort/timeline + what this does / does not get you,
    # computed at finalize from the brief. None on a pre-Phase-3 / direct-assembly course = no band.
    scope: CourseScope | None = None
    settings: CourseSettings = Field(default_factory=CourseSettings)
    risk: RiskProfile = Field(default_factory=RiskProfile)
    learner: LearnerModel = Field(default_factory=LearnerModel)
    graph: PrerequisiteGraph = Field(default_factory=PrerequisiteGraph)
    modules: list[Module] = Field(default_factory=list)
    provenance: list[Citation] = Field(default_factory=list)
    # Which provider produced each key-gated capability's contribution (keyless-fallbacks T5):
    # captured at finalize from the run's credential scope and persisted, so a Draft course carries
    # an honest record of the fallback that built it. Empty on pre-T5 / direct-assembly courses.
    build_capabilities: list[CapabilityBuildTag] = Field(default_factory=list)
    status: CourseStatus = CourseStatus.DIAGNOSING
    budget_ledger: BudgetLedger = Field(default_factory=BudgetLedger)
    # The course's opening videos — the V5 Overview section (a SUMMARY trailer + an OVERVIEW intro).
    # None until the build's finalize stitches them (V5-T2); a course built before V5, with video
    # off, or whose course render degraded carries none — the reader shows no Overview section.
    videos: CourseVideos | None = None
    # The course's AI cover image (course-cover-images). None until a cover job settles READY (or on
    # a keyless account, which never enqueues one — the reader shows the Typographic cover instead).
    # Keeps a job_id handle only; the API resolves a fresh signed URL on demand.
    cover: CoverArtifact | None = None
    # The publish gates captured at finalize (course-review-publish): why a course landed in review,
    # so the owner's review drawer can show it. Empty on a course built before this feature or via a
    # direct-assembly path that doesn't run the gates. Rides in the course JSONB payload (no table).
    review_gates: list[ReviewGate] = Field(default_factory=list)

    @field_validator("scope_note")
    @classmethod
    def _drop_legacy_coverage_gap_sentence(cls, value: str) -> str:
        """Strip the pre-#179 coverage-gap sentence on read (see _LEGACY_COVERAGE_GAP_MARKER)."""
        return _without_legacy_coverage_gap_sentence(value)
