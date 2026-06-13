"""Variant coverage (journey final-task rule): the render path works across ≥2 archetype families,
not just one. Each renders a representative scene built from the skill's validated helpers for that
family — proving the toolchain + tokens handle different visual forms. Self-skips without manim."""

import importlib.util
from pathlib import Path

import pytest
from lunaris_video.gates import ensure_style_tokens
from lunaris_video.rendering import SceneRenderer

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("manim") is None,
    reason="render extra not installed (make video-deps)",
)

# Two archetype FAMILIES from the pinned taxonomy, each implemented with that family's known-good
# helpers (make_array pointer-stepping for process/flow; a baseline-grown bar for quantity/data).
_PROCESS_FLOW = """\
from manim import *
from style_tokens import *


class S1Flow(Scene):
    def construct(self):
        title = title_bar("Process")
        cells, idx = make_array([5, 2, 9, 1, 7])
        self.play(FadeIn(title), FadeIn(cells), FadeIn(idx))
        pointer = Triangle(color=ACCENT, fill_opacity=1).scale(0.15).next_to(cells[0], UP)
        self.play(FadeIn(pointer))
        self.play(pointer.animate.next_to(cells[2], UP), run_time=0.5)
        clear_scene(self)
"""

_QUANTITY_DATA = """\
from manim import *
from style_tokens import *


class S1Data(Scene):
    def construct(self):
        title = title_bar("Quantity")
        axes = hand_axes(xtick_labels=[(0.25, "A"), (0.55, "B"), (0.85, "C")], ylabel="value")
        self.play(FadeIn(title), Create(axes))
        ox, oy, w, h = axes.frame
        baseline = Line([ox, oy, 0], [ox + w, oy, 0], color=MUTED, stroke_width=2)
        bar = Rectangle(width=0.5, height=h * 0.7, fill_color=ACCENT, fill_opacity=1)
        bar.set_stroke(width=0)
        bar.move_to([ox + 0.25 * w, oy + h * 0.35, 0])
        self.play(Create(baseline))
        self.play(GrowFromEdge(bar, DOWN))
        clear_scene(self)
"""


@pytest.mark.parametrize(
    ("scene_id", "scene_class", "source"),
    [
        ("S1_flow", "S1Flow", _PROCESS_FLOW),
        ("S1_data", "S1Data", _QUANTITY_DATA),
    ],
)
async def test_each_archetype_family_renders_to_a_real_mp4(
    tmp_path: Path, scene_id: str, scene_class: str, source: str
) -> None:
    # Arrange
    ensure_style_tokens(tmp_path)
    scene_file = tmp_path / f"{scene_id}.py"
    scene_file.write_text(source, encoding="utf-8")

    # Act
    result = await SceneRenderer().render(scene_file, scene_class)

    # Assert — a real MP4 for this archetype family.
    assert result.succeeded, result.error_tail
    assert result.mp4_path is not None
    assert b"ftyp" in result.mp4_path.read_bytes()[:64]
