"""CQ Phase 3.1 (T2) — the hybrid scope-band polish layer.

The deterministic estimator computes the *facts* (effort band, the count and meaning of the
delivers/excludes lines). An optional key-gated LLM step may refine only the *wording* of those
lines — never the effort, never the line count, never invent a promise. ``reconcile_scope`` enforces
that in code, so a drifting model can't change the facts; these tests pin that guarantee and the
parser/stub/Claude collaborators around it.
"""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from lunaris_agent.subagents.scope_polisher import (
    StubScopePolisher,
    build_polish_prompt,
    parse_polished_lines,
    reconcile_scope,
)
from lunaris_agent.subagents.scope_polisher.claude import ClaudeScopePolisher
from lunaris_runtime.schema import CourseBrief, CourseScope, GoalType, Level


class _RaisingModel:
    """A chat model whose ``ainvoke`` always raises — proves the polisher swallows model errors."""

    async def ainvoke(self, *_args: object, **_kwargs: object) -> object:
        raise RuntimeError("simulated rate-limit / network failure")


def _scope() -> CourseScope:
    return CourseScope(
        effort="About 4-9 weeks of self-paced study (~20-35 hours).",
        delivers=["A structured understanding of X.", "5 modules sequenced by prerequisite."],
        excludes=["It will not certify you."],
    )


def _model(json_text: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(content=json_text)]))


# --- reconcile_scope: the facts-immutable guarantee --------------------------------------------


def test_reconcile_keeps_the_original_effort_even_if_the_candidate_changed_it() -> None:
    original = _scope()
    candidate = CourseScope(
        effort="OVERNIGHT, trust me!", delivers=original.delivers, excludes=original.excludes
    )
    result = reconcile_scope(original, candidate)
    assert result.effort == original.effort


def test_reconcile_accepts_same_count_reworded_lines() -> None:
    original = _scope()
    candidate = CourseScope(
        effort="ignored",
        delivers=["You'll really get X.", "Five prerequisite-ordered modules."],
        excludes=["No certificate is issued."],
    )
    result = reconcile_scope(original, candidate)
    assert result.effort == original.effort  # effort is always the deterministic original
    assert result.delivers == candidate.delivers
    assert result.excludes == candidate.excludes


def test_reconcile_rejects_a_changed_line_count() -> None:
    # The model added a third delivers line (an invented promise) — drop the whole candidate list.
    original = _scope()
    candidate = CourseScope(
        effort="ignored",
        delivers=["a", "b", "AND a free pony"],
        excludes=original.excludes,
    )
    result = reconcile_scope(original, candidate)
    assert result.delivers == original.delivers


def test_reconcile_rejects_a_blank_line() -> None:
    original = _scope()
    candidate = CourseScope(effort="x", delivers=["", "   "], excludes=original.excludes)
    result = reconcile_scope(original, candidate)
    assert result.delivers == original.delivers  # blanked → fall back to the deterministic lines
    assert result.excludes == original.excludes  # same-count, unchanged
    assert result.effort == original.effort


# --- parse_polished_lines: tolerant JSON extraction ---------------------------------------------


def test_parser_reads_a_clean_json_object() -> None:
    parsed = parse_polished_lines('{"delivers": ["a", "b"], "excludes": ["c"]}')
    assert parsed == (["a", "b"], ["c"])


def test_parser_tolerates_prose_and_code_fences_around_the_json() -> None:
    raw = 'Sure!\n```json\n{"delivers": ["a"], "excludes": ["c", "d"]}\n```\nHope that helps.'
    parsed = parse_polished_lines(raw)
    assert parsed == (["a"], ["c", "d"])


def test_parser_returns_none_on_garbage() -> None:
    assert parse_polished_lines("not json at all") is None


# --- build_polish_prompt: brief context ---------------------------------------------------------


def test_prompt_embeds_brief_context_when_provided() -> None:
    brief = CourseBrief(
        subject="AWS Solutions Architect",
        goal="pass the exam",
        goal_type=GoalType.CREDENTIAL,
        target_level=Level.INTERMEDIATE,
    )
    prompt = build_polish_prompt(_scope(), brief)
    assert "AWS Solutions Architect" in prompt
    assert "credential" in prompt.lower()


def test_prompt_omits_brief_context_with_no_brief() -> None:
    prompt = build_polish_prompt(_scope(), None)
    assert "For context" not in prompt


# --- StubScopePolisher: the identity (no-key / test default) ------------------------------------


async def test_stub_polisher_returns_the_scope_unchanged() -> None:
    original = _scope()
    polished = await StubScopePolisher().polish(original, brief=None)
    assert polished == original


# --- ClaudeScopePolisher: refines wording, never facts ------------------------------------------


async def test_claude_polisher_applies_same_shape_rewording() -> None:
    original = _scope()
    model = _model(
        '{"delivers": ["Crisper X.", "Five ordered modules."], "excludes": ["No cert."]}'
    )
    polished = await ClaudeScopePolisher(model).polish(original, brief=None)
    assert polished.effort == original.effort  # effort never polished
    assert polished.delivers == ["Crisper X.", "Five ordered modules."]
    assert polished.excludes == ["No cert."]


async def test_claude_polisher_discards_a_model_that_drifts_the_facts() -> None:
    # The model tries to change the effort AND add a delivers line — reconcile keeps the facts.
    original = _scope()
    model = _model('{"delivers": ["a", "b", "and a bonus!"], "excludes": ["No cert."]}')
    polished = await ClaudeScopePolisher(model).polish(original, brief=None)
    assert polished.effort == original.effort
    assert polished.delivers == original.delivers  # count mismatch rejected
    assert polished.excludes == ["No cert."]  # same count accepted


async def test_claude_polisher_falls_back_to_the_deterministic_band_on_garbage() -> None:
    original = _scope()
    polished = await ClaudeScopePolisher(_model("the model rambled, no json")).polish(
        original, brief=None
    )
    assert polished == original


async def test_claude_polisher_never_raises_into_finalize_when_the_model_errors() -> None:
    # The best-effort contract: a rate-limit / network failure must degrade to the deterministic
    # band, never propagate and break the build.
    original = _scope()
    polished = await ClaudeScopePolisher(_RaisingModel()).polish(original, brief=None)
    assert polished == original
