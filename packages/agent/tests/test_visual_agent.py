from pathlib import Path

import pytest
from lunaris_agent.subagents.visual_agent import (
    MermaidRenderer,
    PassthroughDiagramRenderer,
    StubDiagramRenderer,
    StubVisualGenerator,
    VisualDraft,
    VisualEngine,
    parse_visual,
    parse_visual_spec,
)
from lunaris_runtime.schema import (
    Course,
    FlowNode,
    FlowSpec,
    Lesson,
    MerrillSegments,
    Module,
    Segment,
    StepsSpec,
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


# ─── visual-spec parser ────────────────────────────────────────────────────────
def test_parse_visual_spec_parses_a_fenced_flow_spec() -> None:
    spec = parse_visual_spec(
        'Here:\n```json\n{"type":"flow","nodes":[{"id":"a","label":"A"}],"edges":[]}\n```'
    )

    assert isinstance(spec, FlowSpec)
    assert spec.nodes[0].label == "A"
    assert spec.edges == []


def test_parse_visual_spec_accepts_bare_json_for_steps() -> None:
    spec = parse_visual_spec('{"type":"steps","steps":[{"title":"One"}]}')

    assert isinstance(spec, StepsSpec)
    assert spec.steps[0].title == "One"


def test_parse_visual_spec_returns_none_for_explicit_none() -> None:
    assert parse_visual_spec("NONE") is None


def test_parse_visual_spec_returns_none_for_non_json_text() -> None:
    assert parse_visual_spec("not json at all") is None


def test_parse_visual_spec_rejects_an_unknown_discriminator() -> None:
    # Safety gate: an invented "type" must not produce any spec — the agent cannot talk its way
    # past validation with a discriminator outside the union.
    assert parse_visual_spec('{"type":"bogus","x":1}') is None


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        ('{"type":"flow","nodes":[],"edges":[]}', "flow"),
        ('{"type":"tree","nodes":[]}', "tree"),
        ('{"type":"steps","steps":[]}', "steps"),
        ('{"type":"comparison","columns":[],"rows":[]}', "comparison"),
        ('{"type":"timeline","events":[]}', "timeline"),
    ],
)
def test_parse_visual_spec_covers_every_variant(payload: str, expected_type: str) -> None:
    # Variant coverage: every member of the VisualSpec union is selected by its discriminator.
    spec = parse_visual_spec(payload)

    assert spec is not None
    assert spec.type == expected_type


# ─── stub renderer ───────────────────────────────────────────────────────────
async def test_stub_renderer_succeeds_on_a_valid_diagram() -> None:
    result = await StubDiagramRenderer().render(_VALID_DIAGRAM)

    assert result.ok
    assert result.path is not None and result.path.endswith(".svg")


async def test_stub_renderer_fails_on_unrecognised_source() -> None:
    assert not (await StubDiagramRenderer().render("not a diagram")).ok


# ─── passthrough renderer (no-toolchain fallback) ─────────────────────────────
async def test_passthrough_renderer_accepts_a_valid_diagram_without_a_path() -> None:
    # The no-toolchain fallback validates the source syntactically and ships it un-rendered:
    # ok=True so the engine attaches the visual, path=None because no SVG was produced.
    result = await PassthroughDiagramRenderer().render(_VALID_DIAGRAM)

    assert result.ok is True
    assert result.path is None


async def test_passthrough_renderer_rejects_unrecognised_source() -> None:
    # Prose / malformed blocks are still rejected, exactly as the real renderers do — the
    # fallback ships diagram-as-code, never arbitrary text.
    result = await PassthroughDiagramRenderer().render("just some prose, not a diagram")

    assert result.ok is False
    assert result.error is not None


async def test_engine_ships_a_source_diagram_via_passthrough_unrendered() -> None:
    # Arrange — the no-script fallback path: a source-only diagram with the passthrough renderer.
    course = _course_with_lessons()
    engine = VisualEngine(StubVisualGenerator(), PassthroughDiagramRenderer())

    # Act
    placed = await engine.illustrate(course)

    # Assert — the diagram ships (the web draws from source via MermaidFallback) but carries no
    # render path, since no SVG toolchain ran.
    assert placed == 1
    visual = course.modules[0].lessons[0].segments.demonstrate.visuals[0]
    assert visual.kind is VisualKind.MERMAID
    assert visual.source
    assert visual.rendered is None


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


async def test_engine_threads_a_visual_spec_onto_the_rendered_visual() -> None:
    # Arrange — a draft with both Mermaid source (render gate) and a branded spec.
    course = _course_with_lessons()
    spec = FlowSpec(nodes=[FlowNode(id="a", label="A")])
    generator = StubVisualGenerator(lambda _c, _x: VisualDraft(_VALID_DIAGRAM, spec=spec))
    engine = VisualEngine(generator, StubDiagramRenderer())

    # Act
    placed = await engine.illustrate(course)

    # Assert — the source still renders AND the spec rides along.
    assert placed == 1
    visual = course.modules[0].lessons[0].segments.demonstrate.visuals[0]
    assert visual.spec is spec
    assert visual.rendered is not None


async def test_engine_ships_a_spec_only_visual_without_rendering() -> None:
    # Arrange — a spec with no Mermaid source; the renderer would fail if it were called.
    course = _course_with_lessons()
    spec = FlowSpec(nodes=[FlowNode(id="a", label="A")])
    generator = StubVisualGenerator(lambda _c, _x: VisualDraft("", spec=spec))
    engine = VisualEngine(generator, StubDiagramRenderer(fail_on="graph"))

    # Act
    placed = await engine.illustrate(course)

    # Assert — the spec is self-contained, so it ships without a render path.
    assert placed == 1
    visual = course.modules[0].lessons[0].segments.demonstrate.visuals[0]
    assert visual.spec is spec
    assert visual.rendered is None


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
