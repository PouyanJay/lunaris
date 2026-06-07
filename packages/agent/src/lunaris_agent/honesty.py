"""The honesty gate (CQ Phase 1.6): don't ship confident generic prose as if it were grounded.

When a goal declares it ``needs_research`` (an externally-defined standard/exam/certification) but
the research stage could not ground it, the course is a general introduction — NOT an authoritative
guide to the standard. This computes an honest caveat + whether to withhold publication, so the
finalize step labels and scopes the course rather than presenting model-memory content as the real
standard. Pure + deterministic; the finalize tool applies it.
"""

from dataclasses import dataclass

from lunaris_runtime.schema import CourseBrief, ResearchStatus


@dataclass(frozen=True)
class _GroundingHonesty:
    """The honesty verdict: a learner-facing ``caveat`` (empty = none) and whether the course should
    be withheld from publication (``needs_review``) because grounding it promised wasn't delivered.

    Module-private — callers read ``.caveat`` / ``.needs_review`` off the returned value rather than
    importing the type (one public export per file)."""

    caveat: str = ""
    needs_review: bool = False


def _standard_name(brief: CourseBrief) -> str:
    return brief.target_standard.name if brief.target_standard else "its target standard"


def assess_grounding_honesty(brief: CourseBrief | None) -> _GroundingHonesty:
    """The honesty verdict for a build: a learner-facing caveat + whether to withhold publication.

    Gates only ``needs_research`` goals (a knowledge goal with no external standard has nothing to
    be dishonest about). UNAVAILABLE/missing research → caveat + withhold; PARTIAL → caveat but
    publish; COMPLETE / non-research-needing / no brief → no caveat.
    """
    if brief is None or not brief.needs_research:
        return _GroundingHonesty()
    research = brief.research
    status = research.status if research is not None else ResearchStatus.UNAVAILABLE
    if status is ResearchStatus.UNAVAILABLE:
        return _GroundingHonesty(
            caveat=(
                f"This course could not be grounded in {_standard_name(brief)}'s real requirements "
                "(research was unavailable). Treat it as a general introduction, not an "
                "authoritative guide to the standard."
            ),
            needs_review=True,
        )
    if status is ResearchStatus.PARTIAL:
        return _GroundingHonesty(
            caveat=(
                f"This course is only partially grounded in {_standard_name(brief)}'s real "
                "requirements; some content reflects general knowledge rather than the standard."
            ),
            needs_review=False,
        )
    return _GroundingHonesty()
