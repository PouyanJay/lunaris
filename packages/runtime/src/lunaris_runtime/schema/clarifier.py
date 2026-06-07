"""The interpret-clarifier contract (P7.5): the learner's opt-in confirm answers (later, questions).

After the goal interpreter infers a :class:`CourseBrief`, the build can offer a short, OPT-IN
clarifier — a few questions, each with the inferred value pre-picked as the Recommended option — so
the learner confirms or adjusts the interpretation before building. The confirmed answers
(:class:`Clarification`) merge onto the brief (``lunaris_runtime.clarifier.apply_clarification``),
sharpening the frontier (what to skip) and the authoring voice. Every field is optional: an empty or
absent :class:`Clarification` means "accept the inference" — the zero-friction default that
reproduces today's inferred-only build.
"""

from pydantic import Field

from .base import CourseModel
from .enums import ClarifierKind, DetailDepth, GoalType, LanguageStyle, Level

# The free-text fields fold into the brief and travel into LLM prompts, so they are bounded at the
# schema level (defence in depth — independent of the HTTP query-param cap) against a prompt-bloat /
# injection surface on the POST body path. Generous for a human self-report, far under the URL cap.
_MAX_FREE_TEXT_CHARS = 1000


class Clarification(CourseModel):
    """A learner's confirmed/adjusted answers to the interpret clarifier (opt-in; all optional).

    Merged onto the inferred brief before the build. ``goal_type`` confirms or overrides what kind
    of outcome the goal is (CQ Phase 1 — drives deliverable shape + research depth);
    ``target_level`` confirms or overrides the level; ``assumed_known`` (the learner's current topic
    knowledge) folds into ``assumed_prior`` so the existing profiler sharpens the frontier;
    ``background`` folds into ``audience``; ``detail_depth`` / ``language_style`` override the
    authoring preferences. Any field left unset keeps the interpreter's inference.
    """

    goal_type: GoalType | None = None
    target_level: Level | None = None
    assumed_known: str = Field(default="", max_length=_MAX_FREE_TEXT_CHARS)
    background: str = Field(default="", max_length=_MAX_FREE_TEXT_CHARS)
    detail_depth: DetailDepth | None = None
    language_style: LanguageStyle | None = None


class ClarifierOption(CourseModel):
    """One selectable answer for a CHOICE question; ``recommended`` marks the interpreter's guess
    (the value pre-picked in the UI, so the zero-friction path is a single confirm)."""

    value: str
    label: str
    recommended: bool = False


class ClarifierQuestion(CourseModel):
    """A single clarifier question: a closed CHOICE over ``options`` or a free-``TEXT`` field.

    ``id`` names the :class:`Clarification` field the answer populates (``goal`` / ``level`` /
    ``knowledge`` / ``background`` / ``detail`` / ``language``); ``placeholder`` seeds a TEXT field.
    """

    id: str
    prompt: str
    kind: ClarifierKind
    options: list[ClarifierOption] = Field(default_factory=list)
    placeholder: str = ""


class Clarifier(CourseModel):
    """The confirm questions derived from an inferred brief (the 'infer' half of the P7.5 flow).

    Server-derived (``lunaris_runtime.clarifier.build_clarifier``) so the options + the Recommended
    pre-pick stay in lockstep with the backend enums; the web renders the questions generically.
    """

    questions: list[ClarifierQuestion]
