"""P5: the composition root always wires a visual engine, choosing the renderer from the
environment — the real ``MermaidRenderer`` when ``LUNARIS_MERMAID_SCRIPT`` is set, else the
no-toolchain ``PassthroughDiagramRenderer`` so branded visuals ship without a render script."""

import pytest
from lunaris_agent.composition import _visual_engine_from_env
from lunaris_agent.subagents.visual_agent import (
    MermaidRenderer,
    PassthroughDiagramRenderer,
    VisualEngine,
)

_WORKER = "claude-haiku-4-5-20251001"


def test_visual_engine_uses_passthrough_when_no_render_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — no render toolchain configured.
    monkeypatch.delenv("LUNARIS_MERMAID_SCRIPT", raising=False)

    # Act
    engine = _visual_engine_from_env(_WORKER)

    # Assert — an engine is always returned (visuals are on by default), backed by the passthrough
    # renderer so a course still ships its diagrams without an SVG toolchain.
    assert isinstance(engine, VisualEngine)
    assert isinstance(engine.renderer, PassthroughDiagramRenderer)


def test_visual_engine_uses_mermaid_renderer_when_script_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — the beautiful-mermaid render script is configured (npx tsx runtime on this machine).
    monkeypatch.setenv("LUNARIS_MERMAID_SCRIPT", "render.ts")
    monkeypatch.setenv("LUNARIS_MERMAID_RUNTIME", "npx tsx")

    # Act
    engine = _visual_engine_from_env(_WORKER)

    # Assert — the live renderer that shells out to produce a validated SVG.
    assert isinstance(engine, VisualEngine)
    assert isinstance(engine.renderer, MermaidRenderer)
