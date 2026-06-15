"""Validated-helper tests for the generated ``style_tokens.py`` — the deterministic layout
primitives the codegen calls instead of hand-placing mobjects.

These exec the ACTUAL sandbox file (``render_style_tokens_source()`` — the pinned asset with token
values swapped) and assert the helpers produce frame-fitting, well-structured geometry. They need
manim, which CI installs without (``make video-deps`` makes a dev machine capable), so they
self-skip there — same gate as the render-smoke tests."""

import importlib.util
import tempfile
from itertools import pairwise
from typing import Any

import pytest
from lunaris_video.style import render_style_tokens_source

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("manim") is None,
    reason="render extra not installed (make video-deps)",
)

# A safe margin: a helper that "fits" must sit inside the frame with breathing room, not flush to
# the edge (Gate B rejects anything clipped within ~0.4 units of the edge).
_MARGIN = 0.4
# A centred group should land on ORIGIN to within rounding — far tighter than the frame margin.
_CENTER_TOLERANCE = 0.05


def _style_namespace() -> dict[str, Any]:
    """Exec the real sandbox style_tokens.py and return its namespace (helpers + manim names)."""
    namespace: dict[str, Any] = {}
    exec(render_style_tokens_source(), namespace)  # executing our own generated source
    # Building Text mobjects caches SVGs to manim's media dir (cwd by default) — keep that out of
    # the repo by pointing it at a throwaway temp dir before any helper renders text.
    namespace["config"].media_dir = tempfile.mkdtemp(prefix="lunaris_style_test_")
    return namespace


def test_hero_title_scales_a_long_headline_to_fit_the_frame() -> None:
    # Arrange
    ns = _style_namespace()
    frame_width = ns["config"].frame_width

    # Act — a headline far too wide to fit at its native size.
    title = ns["hero_title"]("A Hook Headline That Is Far Too Long To Fit Across One Video Frame")

    # Assert — the helper scaled it inside the frame; the #1 hook defect (edge clip) cannot occur.
    assert title.width <= frame_width - _MARGIN


def test_hero_title_stacks_kicker_headline_and_subtitle_centered() -> None:
    # Arrange
    ns = _style_namespace()

    # Act
    title = ns["hero_title"]("The Headline", subtitle="a quiet subtitle", kicker="LESSON 1")

    # Assert — three stacked lines, centered on the frame (no off-center drift).
    assert len(title.submobjects) == 3
    assert abs(title.get_center()[0]) < _CENTER_TOLERANCE
    assert abs(title.get_center()[1]) < _CENTER_TOLERANCE


def test_make_network_node_count_matches_layer_sizes() -> None:
    # Arrange
    ns = _style_namespace()
    layer_sizes = [3, 5, 5, 2]

    # Act
    net = ns["make_network"](layer_sizes)

    # Assert — one node per requested unit, one column per layer.
    assert len(net.nodes) == sum(layer_sizes)
    assert len(net.layers) == len(layer_sizes)


def test_make_network_connects_consecutive_layers_fully() -> None:
    # Arrange
    ns = _style_namespace()
    layer_sizes = [3, 4, 2]

    # Act
    net = ns["make_network"](layer_sizes)

    # Assert — every node wires to every node in the next layer: 3*4 + 4*2 = 20 edges.
    expected_edges = sum(a * b for a, b in pairwise(layer_sizes))
    assert len(net.edges) == expected_edges


def test_make_network_fits_the_frame_even_for_a_dense_graph() -> None:
    # Arrange
    ns = _style_namespace()
    config = ns["config"]

    # Act — a deliberately dense network that would overflow if laid out naively.
    net = ns["make_network"]([6, 8, 8, 6])

    # Assert — the whole graph sits inside the frame with margin (no crammed-into-one-side render).
    assert net.width <= config.frame_width - _MARGIN
    assert net.height <= config.frame_height - _MARGIN
