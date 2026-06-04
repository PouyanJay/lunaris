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
from .enums import DetailDepth, LanguageStyle, Level

# The free-text fields fold into the brief and travel into LLM prompts, so they are bounded at the
# schema level (defence in depth — independent of the HTTP query-param cap) against a prompt-bloat /
# injection surface on the POST body path. Generous for a human self-report, far under the URL cap.
_MAX_FREE_TEXT_CHARS = 1000


class Clarification(CourseModel):
    """A learner's confirmed/adjusted answers to the interpret clarifier (opt-in; all optional).

    Merged onto the inferred brief before the build. ``target_level`` confirms or overrides the
    level; ``assumed_known`` (the learner's current topic knowledge) folds into ``assumed_prior`` so
    the existing profiler sharpens the frontier; ``background`` folds into ``audience``;
    ``detail_depth`` / ``language_style`` override the authoring preferences. Any field left unset
    keeps the interpreter's inference.
    """

    target_level: Level | None = None
    assumed_known: str = Field(default="", max_length=_MAX_FREE_TEXT_CHARS)
    background: str = Field(default="", max_length=_MAX_FREE_TEXT_CHARS)
    detail_depth: DetailDepth | None = None
    language_style: LanguageStyle | None = None
