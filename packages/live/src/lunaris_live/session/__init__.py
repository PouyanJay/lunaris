"""Lunaris Live's session runtime — the loop that walks a compiled map with a learner.

Phase 1 built the map (``lunaris_live.graph``); this is what walks it. The graph is a map of the
subject, never a route through the session: the conversation drives, and the map keeps score.

The loop is split along one line — what happens next is a *policy* (``decide_move``: deterministic,
legible, testable without a key) and how it is said is *generative* (``ITutor``: a seam, with a
deterministic implementation for the offline path). The learner model is what connects them: it is
moved by graded evidence, and the director reads it back.
"""

from .apply_evidence import apply_evidence
from .claude_tutor import ClaudeTutor
from .decide_move import decide_move
from .memory_knowledge_store import MemoryKnowledgeStore
from .memory_session_store import MemorySessionStore
from .open_session import open_session
from .protocols import IKnowledgeStore, ISessionStore, ITutor
from .recall_of import recall_of
from .reject_unteachable_move import reject_unteachable_move
from .schema import (
    DirectorMove,
    EvidenceKind,
    LearnerModel,
    MoveKind,
    NodeKnowledge,
    Session,
    SessionClock,
    SessionStatus,
    SessionTurn,
)
from .session_format_error import SessionFormatError
from .stub_tutor import StubTutor
from .supabase_knowledge_store import SupabaseKnowledgeStore
from .supabase_session_store import SupabaseSessionStore
from .tutor_unavailable_error import TutorUnavailableError

__all__ = [
    "ClaudeTutor",
    "DirectorMove",
    "EvidenceKind",
    "IKnowledgeStore",
    "ISessionStore",
    "ITutor",
    "LearnerModel",
    "MemoryKnowledgeStore",
    "MemorySessionStore",
    "MoveKind",
    "NodeKnowledge",
    "Session",
    "SessionClock",
    "SessionFormatError",
    "SessionStatus",
    "SessionTurn",
    "StubTutor",
    "SupabaseKnowledgeStore",
    "SupabaseSessionStore",
    "TutorUnavailableError",
    "apply_evidence",
    "decide_move",
    "open_session",
    "recall_of",
    "reject_unteachable_move",
]
