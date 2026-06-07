"""The coverage-judge prompt (CQ Phase 4.2).

Lays the course's modules — what each builds, its objectives, whether it has practice, and a short
content digest — beside the competencies the standard promised, and asks the judge to name the
promised competencies the course does NOT materially build (teach AND practise, not merely mention).
"""

from collections.abc import Sequence

from lunaris_runtime.schema import Module

from ..lesson_claims import lesson_segments

# How much lesson prose to show the judge per module — enough to tell "builds it" from "mentions it"
# without blowing the prompt on a long course.
_DIGEST_CHARS = 320

_TEMPLATE = """You are verifying the COVERAGE of a course against the competencies it promised.

Promised competencies (from the target standard):
{promised}

The course's modules:
{modules}

A competency is COVERED only when some module materially BUILDS it — teaches it AND gives practice
toward it — not merely mentions it in passing. Judge against the content shown, not the titles.

Return ONLY the promised competencies the course does NOT materially build ("promised but not
built"), each with a one-line reason. Respond with ONLY this JSON, no prose:
{{"gaps": [{{"competency": "<verbatim from the list above>", "reason": "..."}}]}}
An empty gaps array means every promised competency is built."""


def _has_practice(module: Module) -> bool:
    """A module practises a competency when a lesson's apply or integrate phase has prose or a
    resource — the two Merrill phases where the learner *does*, not the activate/demonstrate phases
    that recall or instruct."""
    for lesson in module.lessons:
        for phase in (lesson.segments.apply, lesson.segments.integrate):
            if phase.prose.strip() or phase.resources:
                return True
    return False


def _content_digest(module: Module) -> str:
    """A short, bounded sample of the module's teaching prose, so the judge sees what it teaches."""
    prose = " ".join(
        segment.prose.strip()
        for lesson in module.lessons
        for segment in lesson_segments(lesson)
        if segment.prose.strip()
    )
    return prose[:_DIGEST_CHARS] if prose else "(no content authored)"


def _module_block(module: Module) -> str:
    objectives = "; ".join(obj.statement for obj in module.objectives) or "(none)"
    builds = module.competency or "(untagged)"
    practice = "yes" if _has_practice(module) else "no"
    return (
        f'Module "{module.title}" — builds: {builds}\n'
        f"  objectives: {objectives}\n"
        f"  has practice: {practice}\n"
        f"  content: {_content_digest(module)}"
    )


def build_coverage_prompt(competencies: Sequence[str], modules: Sequence[Module]) -> str:
    """The coverage-judge prompt: promised competencies beside what each module actually builds."""
    promised = "\n".join(f"{i + 1}. {competency}" for i, competency in enumerate(competencies))
    module_blocks = "\n\n".join(_module_block(module) for module in modules) or "(no modules)"
    return _TEMPLATE.format(promised=promised, modules=module_blocks)
