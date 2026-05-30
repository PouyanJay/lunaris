from pathlib import Path

from lunaris_agent.subagents.visual_agent import (
    MermaidRenderer,
    StubDiagramRenderer,
    StubVisualGenerator,
    VisualDraft,
    VisualEngine,
    parse_visual,
)
from lunaris_runtime.schema import (
    Course,
    Lesson,
    MerrillSegments,
    Module,
    Segment,
    VisualKind,
)

_VALID_DIAGRAM = "graph TD\n  A-->B"


# ─── parser ──────────────────────────────────────────────────────────────────
def test_parse_visual_extracts_a_fenced_mermaid_block() -> None:
    draft = parse_visual("Here is the diagram:\n```mermaid\ngraph TD; A-->B\n```\n")

    assert draft is not None
    assert draft.source == "graph TD; A-->B"


def test_parse_visual_accepts_bare_source() -> None:
    draft = parse_visual("flowchart LR\n  A --> B")

    assert draft is not None
    assert draft.source == "flowchart LR\n  A --> B"


def test_parse_visual_returns_none_for_explicit_none() -> None:
    assert parse_visual("NONE") is None


def test_parse_visual_returns_none_for_unrecognised_diagram() -> None:
    assert parse_visual("```\njust some prose, not a diagram\n```") is None


def test_parse_visual_rejects_a_graph_lookalike() -> None:
    # "graphQL" must not slip past the "graph" diagram type
    assert parse_visual("graphQL TD\n  A-->B") is None


# ─── stub renderer ───────────────────────────────────────────────────────────
async def test_stub_renderer_succeeds_on_a_valid_diagram() -> None:
    result = await StubDiagramRenderer().render(_VALID_DIAGRAM)

    assert result.ok
    assert result.path is not None and result.path.endswith(".svg")


async def test_stub_renderer_fails_on_unrecognised_source() -> None:
    assert not (await StubDiagramRenderer().render("not a diagram")).ok


# ─── mermaid renderer (live impl) ────────────────────────────────────────────
async def test_mermaid_renderer_never_raises_when_the_runtime_is_missing(tmp_path: Path) -> None:
    # A missing runtime binary must surface as ok=False, never an exception (the engine
    # relies on this to repair/skip rather than crash the run).
    renderer = MermaidRenderer(
        tmp_path / "render.ts", tmp_path, runtime=("definitely-not-a-real-binary-xyz",)
    )

    result = await renderer.render(_VALID_DIAGRAM)

    assert result.ok is False
    assert result.error is not None


# ─── engine ──────────────────────────────────────────────────────────────────
def _course_with_lessons(module_count: int = 1) -> Course:
    def _module(index: int) -> Module:
        blank = Segment(prose="")
        lesson = Lesson(
            id=f"m{index}-l0",
            segments=MerrillSegments(
                activate=blank,
                demonstrate=Segment(prose="the core teaching"),
                apply=blank,
                integrate=blank,
            ),
        )
        return Module(id=f"m{index}", title=f"Concept {index}", lessons=[lesson])

    return Course(id="c", topic="t", modules=[_module(i) for i in range(module_count)])


async def test_engine_attaches_a_validated_visual() -> None:
    # Arrange — generator yields a diagram, stub renderer validates it
    course = _course_with_lessons()
    engine = VisualEngine(StubVisualGenerator(), StubDiagramRenderer())

    # Act
    placed = await engine.illustrate(course)

    # Assert — one Mermaid visual on the demonstrate segment, carrying a render path
    assert placed == 1
    visual = course.modules[0].lessons[0].segments.demonstrate.visuals[0]
    assert visual.kind is VisualKind.MERMAID
    assert visual.rendered is not None
    assert visual.mayer_checks.coherence is True


async def test_engine_places_a_visual_on_every_module() -> None:
    # Arrange — two modules, each with a lesson
    course = _course_with_lessons(module_count=2)
    engine = VisualEngine(StubVisualGenerator(), StubDiagramRenderer())

    # Act
    placed = await engine.illustrate(course)

    # Assert — count accumulates and each module's segment got its own visual
    assert placed == 2
    assert all(module.lessons[0].segments.demonstrate.visuals for module in course.modules)


async def test_engine_places_nothing_when_no_diagram_is_warranted() -> None:
    # Arrange — generator declines (coherence: decorative diagrams are skipped)
    course = _course_with_lessons()
    engine = VisualEngine(StubVisualGenerator(lambda _c, _x: None), StubDiagramRenderer())

    # Act
    placed = await engine.illustrate(course)

    # Assert
    assert placed == 0
    assert course.modules[0].lessons[0].segments.demonstrate.visuals == []


async def test_engine_repairs_then_succeeds_on_the_second_attempt() -> None:
    # Arrange — generator yields an unrenderable diagram first, a valid one on repair
    course = _course_with_lessons()
    drafts = iter([VisualDraft("not a diagram"), VisualDraft(_VALID_DIAGRAM)])
    calls = {"n": 0}

    def generate(_concept: str, _context: str) -> VisualDraft:
        calls["n"] += 1
        return next(drafts)

    engine = VisualEngine(StubVisualGenerator(generate), StubDiagramRenderer(), max_repairs=1)

    # Act
    placed = await engine.illustrate(course)

    # Assert — the repair pass produced a renderable diagram
    assert placed == 1
    assert calls["n"] == 2


async def test_engine_skips_after_exhausting_repairs() -> None:
    # Arrange — renderer always fails; count generator calls to prove repair was attempted
    course = _course_with_lessons()
    calls = {"n": 0}

    def generate(_concept: str, _context: str) -> VisualDraft:
        calls["n"] += 1
        return VisualDraft(_VALID_DIAGRAM)

    engine = VisualEngine(
        StubVisualGenerator(generate), StubDiagramRenderer(fail_on="graph"), max_repairs=1
    )

    # Act
    placed = await engine.illustrate(course)

    # Assert — no broken diagram ships, and a repair was attempted (initial + 1 repair)
    assert placed == 0
    assert course.modules[0].lessons[0].segments.demonstrate.visuals == []
    assert calls["n"] == 2
