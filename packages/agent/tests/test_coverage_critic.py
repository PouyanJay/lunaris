"""CQ Phase 4.2 — the coverage critic: every promised competency is materially built, or scoped out.

The coverage critic is the third finalize gate — distinct from the claim ``Verifier`` moat and the
structural ``MinimalCritic``. Per owner Q2 the primary is an LLM judge; a deterministic fail-safe
keeps keyless builds running and offline tests green (AD2). These tests pin both: the deterministic
structural check, the Claude judge's parse, and its fall-back-to-deterministic guarantee — none
needs a real key.
"""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from lunaris_agent.coverage_critic import (
    ClaudeCoverageCritic,
    DeterministicCoverageCritic,
    build_coverage_prompt,
)
from lunaris_runtime.schema import (
    Course,
    CourseBrief,
    Level,
    Module,
    ResearchSource,
    ResearchStatus,
    StandardResearch,
)


def _brief(competencies: list[str]) -> CourseBrief:
    return CourseBrief(
        subject="s",
        goal="g",
        target_level=Level.ADVANCED,
        research=StandardResearch(
            status=ResearchStatus.COMPLETE,
            competencies=competencies,
            sources=[ResearchSource(url="https://example.org/standard")],
        ),
    )


def _course(module_competencies: list[str]) -> Course:
    """A course whose modules are each tagged with one researched competency (P7.3)."""
    modules = [
        Module(id=f"m{i}", title=f"M{i}", competency=competency)
        for i, competency in enumerate(module_competencies)
    ]
    return Course(id="c", topic="t", modules=modules)


def _model(json_text: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(content=json_text)]))


class _RaisingModel:
    """A chat model whose ``ainvoke`` always raises — proves the critic falls back, not crashes."""

    async def ainvoke(self, *_args: object, **_kwargs: object) -> object:
        raise RuntimeError("simulated rate-limit / network failure")


class _NeverCalledModel:
    """A chat model that fails the test if invoked — proves no LLM call when nothing is promised."""

    async def ainvoke(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("the coverage critic must not call the model with no competencies")


# --- the deterministic fail-safe (structural coverage) -------------------------------------------


async def test_deterministic_flags_a_competency_no_module_builds() -> None:
    # Arrange — two competencies promised, only one tagged to a module.
    critic = DeterministicCoverageCritic()

    # Act
    report = await critic.review(_course(["alpha"]), brief=_brief(["alpha", "beta"]))

    # Assert — the untagged competency is the lone gap (promised but not built).
    assert [gap.competency for gap in report.gaps] == ["beta"]


async def test_deterministic_is_clean_when_every_competency_is_tagged() -> None:
    # Arrange
    critic = DeterministicCoverageCritic()

    # Act
    report = await critic.review(_course(["alpha", "beta"]), brief=_brief(["alpha", "beta"]))

    # Assert
    assert report.is_clean


async def test_deterministic_is_clean_without_research() -> None:
    # No research / no brief → nothing was promised, so there is no gap to flag either way.
    # Arrange
    critic = DeterministicCoverageCritic()

    # Act / Assert — both degenerate inputs (a brief without research, and no brief) are clean.
    no_research = await critic.review(_course(["alpha"]), brief=CourseBrief(subject="s", goal="g"))
    no_brief = await critic.review(_course([]), brief=None)
    assert no_research.is_clean
    assert no_brief.is_clean


# --- the LLM judge (primary) ---------------------------------------------------------------------


async def test_claude_flags_an_unbuilt_competency_from_its_verdict() -> None:
    # Arrange — the judge rules "beta" only mentioned, no practice; both are tagged so the
    # deterministic check alone would pass — proving the LLM judge's verdict is what's used.
    critic = ClaudeCoverageCritic(
        _model('{"gaps": [{"competency": "beta", "reason": "only mentioned, no practice"}]}')
    )

    # Act
    report = await critic.review(_course(["alpha", "beta"]), brief=_brief(["alpha", "beta"]))

    # Assert
    assert [gap.competency for gap in report.gaps] == ["beta"]
    assert "practice" in report.gaps[0].reason


async def test_claude_ignores_a_gap_for_an_unpromised_competency() -> None:
    # The judge hallucinates a gap for a competency that was never promised → it is dropped, so the
    # critic can only ever flag real promises.
    # Arrange
    critic = ClaudeCoverageCritic(_model('{"gaps": [{"competency": "invented", "reason": "x"}]}'))

    # Act
    report = await critic.review(_course(["alpha"]), brief=_brief(["alpha"]))

    # Assert
    assert report.is_clean


async def test_claude_falls_back_to_deterministic_on_model_error() -> None:
    # The model raises → the critic falls back to the deterministic structural check, which flags
    # the untagged "beta" rather than crashing the build (the fail-safe).
    critic = ClaudeCoverageCritic(_RaisingModel())

    report = await critic.review(_course(["alpha"]), brief=_brief(["alpha", "beta"]))

    assert [gap.competency for gap in report.gaps] == ["beta"]


async def test_claude_is_clean_and_makes_no_call_without_competencies() -> None:
    # Nothing promised → clean with no LLM call (the model would assert if invoked).
    # Arrange
    critic = ClaudeCoverageCritic(_NeverCalledModel())

    # Act
    report = await critic.review(_course([]), brief=CourseBrief(subject="s", goal="g"))

    # Assert
    assert report.is_clean


async def test_claude_falls_back_when_the_reply_is_unparseable() -> None:
    # An unparseable reply (no JSON) degrades to the deterministic check — not a crash, not clean.
    # Arrange
    critic = ClaudeCoverageCritic(_model("I could not produce JSON, sorry."))

    # Act
    report = await critic.review(_course(["alpha"]), brief=_brief(["alpha", "beta"]))

    # Assert
    assert [gap.competency for gap in report.gaps] == ["beta"]


# --- the prompt ----------------------------------------------------------------------------------


def test_build_coverage_prompt_presents_the_promised_competencies_and_modules() -> None:
    prompt = build_coverage_prompt(
        ["hear implied intent in speech", "adapt register live in speech"],
        _course(["hear implied intent in speech"]).modules,
    )

    assert "hear implied intent in speech" in prompt
    assert "adapt register live in speech" in prompt
    assert "M0" in prompt  # the module title reaches the judge
