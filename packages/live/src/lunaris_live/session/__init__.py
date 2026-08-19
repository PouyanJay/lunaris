"""Lunaris Live's session runtime — the loop that walks a compiled map with a learner.

Phase 1 built the map (``lunaris_live.graph``); this is what walks it. The graph is a map of the
subject, never a route through the session: the conversation drives, and the map keeps score.

The loop is split along one line — what happens next is a *policy* (``decide_move``: deterministic,
legible, testable without a key) and how it is said is *generative* (``ITutor``: a seam, with a
deterministic implementation for the offline path). The learner model is what connects them: it is
moved by graded evidence, and the director reads it back.
"""

from .apply_evidence import apply_evidence
from .claude_grader import ClaudeGrader
from .claude_tutor import ClaudeTutor
from .compose_layout import compose_layout
from .decide_move import decide_move
from .grader_unavailable_error import GraderUnavailableError
from .mastery_thresholds import DECAYED, MASTERED
from .max_answer_chars import MAX_ANSWER_CHARS
from .memory_knowledge_store import MemoryKnowledgeStore
from .memory_session_store import MemorySessionStore
from .open_placement import open_placement
from .open_session import open_session
from .placement_not_answerable_error import PlacementNotAnswerableError
from .protocols import (
    IGrader,
    IInterviewer,
    IKnowledgeStore,
    ISessionStore,
    ISimRegistry,
    ITutor,
    ITutorDeltaSink,
)
from .recall_of import recall_of
from .reject_unteachable_move import reject_unteachable_move
from .relay_delta import relay_delta
from .resolve_sim_app import resolve_sim_app
from .schema import (
    ConceptMapCard,
    CriterionCard,
    DirectorMove,
    EvidenceKind,
    ExampleBlock,
    ExplainBack,
    HintBlock,
    InterviewExchange,
    LayoutBlock,
    LayoutComponent,
    LayoutSpec,
    LearnerModel,
    LessonParts,
    MasteryMeter,
    MeterEntry,
    MoveKind,
    NodeKnowledge,
    PracticeBlock,
    ProseBlock,
    QuizCard,
    Session,
    SessionClock,
    SessionStatus,
    SessionTurn,
    SimApp,
    SimAppCard,
    StackBlock,
    SurfaceBlock,
    SurfaceKind,
    SurfaceSpec,
    TurnGrade,
    WorkedExample,
)
from .select_surface import select_surface
from .session_closed_error import SessionClosedError
from .session_format_error import SessionFormatError
from .stage_criterion import stage_criterion
from .stale_answer_error import StaleAnswerError
from .stub_grader import StubGrader
from .stub_interviewer import StubInterviewer
from .stub_sim_path import STUB_SIM_PATH
from .stub_sim_registry import StubSimRegistry
from .stub_tutor import StubTutor
from .supabase_knowledge_store import SupabaseKnowledgeStore
from .supabase_session_store import SupabaseSessionStore
from .take_turn import take_turn
from .turn_outcome import TurnOutcome
from .tutor_unavailable_error import TutorUnavailableError

__all__ = [
    "DECAYED",
    "MASTERED",
    "MAX_ANSWER_CHARS",
    "STUB_SIM_PATH",
    "ClaudeGrader",
    "ClaudeTutor",
    "ConceptMapCard",
    "CriterionCard",
    "DirectorMove",
    "EvidenceKind",
    "ExampleBlock",
    "ExplainBack",
    "GraderUnavailableError",
    "HintBlock",
    "IGrader",
    "IInterviewer",
    "IKnowledgeStore",
    "ISessionStore",
    "ISimRegistry",
    "ITutor",
    "ITutorDeltaSink",
    "InterviewExchange",
    "LayoutBlock",
    "LayoutComponent",
    "LayoutSpec",
    "LearnerModel",
    "LessonParts",
    "MasteryMeter",
    "MemoryKnowledgeStore",
    "MemorySessionStore",
    "MeterEntry",
    "MoveKind",
    "NodeKnowledge",
    "PlacementNotAnswerableError",
    "PracticeBlock",
    "ProseBlock",
    "QuizCard",
    "Session",
    "SessionClock",
    "SessionClosedError",
    "SessionFormatError",
    "SessionStatus",
    "SessionTurn",
    "SimApp",
    "SimAppCard",
    "StackBlock",
    "StaleAnswerError",
    "StubGrader",
    "StubInterviewer",
    "StubSimRegistry",
    "StubTutor",
    "SupabaseKnowledgeStore",
    "SupabaseSessionStore",
    "SurfaceBlock",
    "SurfaceKind",
    "SurfaceSpec",
    "TurnGrade",
    "TurnOutcome",
    "TutorUnavailableError",
    "WorkedExample",
    "apply_evidence",
    "compose_layout",
    "decide_move",
    "open_placement",
    "open_session",
    "recall_of",
    "reject_unteachable_move",
    "relay_delta",
    "resolve_sim_app",
    "select_surface",
    "stage_criterion",
    "take_turn",
]
