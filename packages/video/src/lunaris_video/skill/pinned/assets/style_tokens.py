"""
style_tokens.py — shared design tokens + validated helpers for explainer-video scenes.

Copy this file next to the generated scenes file and `from style_tokens import *`.
When a harness/user supplies a design system, edit ONLY the token values; every scene
inherits the change. Defaults: deep-ink background, amber accent, instrument feel.
"""
from manim import *
import numpy as np

# ----- tokens (edit these to match a project design system) -----
BG      = "#0E1116"   # background
INK     = "#E6EDF3"   # primary text
MUTED   = "#5B6470"   # secondary text, axes, ticks
ACCENT  = "#FBBF24"   # highlight / brand accent
DANGER  = "#F87171"   # negative / eliminated / worse
GREEN   = "#34D399"   # positive / found / better
PANEL   = "#1A2029"   # card & cell fills
ALT     = "#7DD3FC"   # second-series color (vs ACCENT)
FONT    = "DejaVu Sans"  # must exist in render env; check `fc-list`

config.background_color = BG

# ----- validated helpers -----

def title_bar(text, font_size=33):
    """Scene title with accent underline, pinned to top edge."""
    t = Text(text, font_size=font_size, color=INK, weight=BOLD, font=FONT)
    underline = Line(LEFT, RIGHT, color=ACCENT, stroke_width=3)
    underline.set_width(t.width)
    underline.next_to(t, DOWN, buff=0.12)
    return VGroup(t, underline).to_edge(UP, buff=0.45)


def make_array(values, cell=0.82, font_size=22):
    """Indexed cell array for algorithm walkthroughs. Returns (cells, index_labels).
    Fits 15 cells across a 720p frame at default sizes."""
    cells = VGroup()
    for v in values:
        sq = Square(side_length=cell, stroke_color=MUTED, stroke_width=1.6,
                    fill_color=PANEL, fill_opacity=1.0)
        num = Text(str(v), font_size=font_size, color=INK, font=FONT)
        num.scale_to_fit_width(min(num.width, cell * 0.72))  # P6: digit overflow
        cells.add(VGroup(sq, num.move_to(sq)))
    cells.arrange(RIGHT, buff=0.07)
    idx = VGroup(*[
        Text(str(i), font_size=15, color=MUTED, font=FONT).next_to(c, DOWN, buff=0.18)
        for i, c in enumerate(cells)
    ])
    return cells, idx


def hand_axes(ox=-5.4, oy=-1.3, w=10.8, h=2.9,
              xtick_labels=None, ylabel=None):
    """LaTeX-free axes. xtick_labels: list of (fraction_0_to_1, label_str)."""
    g = VGroup(
        Line([ox, oy, 0], [ox + w, oy, 0], color=MUTED, stroke_width=2),
        Line([ox, oy, 0], [ox, oy + h, 0], color=MUTED, stroke_width=2),
    )
    for frac, lab in (xtick_labels or []):
        x = ox + frac * w
        g.add(Line([x, oy, 0], [x, oy - 0.08, 0], color=MUTED, stroke_width=2))
        g.add(Text(lab, font_size=16, color=MUTED, font=FONT).move_to([x, oy - 0.32, 0]))
    if ylabel:
        g.add(Text(ylabel, font_size=16, color=MUTED, font=FONT)
              .rotate(PI / 2).move_to([ox - 0.35, oy + h / 2, 0]))
    g.frame = (ox, oy, w, h)
    return g


def smooth_curve(f, ox, oy, w, h, color=ACCENT, n=120, stroke_width=4):
    """Plot f: [0,1] -> [0,1] inside the (ox, oy, w, h) frame. No LaTeX, no Axes."""
    pts = [[ox + (i / n) * w, oy + float(np.clip(f(i / n), 0, 1)) * h, 0]
           for i in range(n + 1)]
    c = VMobject(stroke_color=color, stroke_width=stroke_width)
    c.set_points_smoothly(pts)
    return c


def pivot_anchor(point):
    """Invisible pivot for rotating groups (P1). Add to the group; rotate
    about_point=anchor.get_center() so the pivot survives group transforms."""
    return Dot(point, radius=0.001, fill_opacity=0, stroke_opacity=0)


def clear_scene(scene, run_time=0.7):
    """Clean concat boundary: fade out everything."""
    if scene.mobjects:
        scene.play(*[FadeOut(m) for m in scene.mobjects], run_time=run_time)


def hero_title(headline, subtitle=None, kicker=None, max_width=None):
    """Centered title card for hook / title scenes. An optional ACCENT kicker (eyebrow) sits above
    and a MUTED subtitle below a bold INK headline; the headline and subtitle scale to fit the
    frame, so a long title can never clip the edges (the #1 hook/title defect). Returns a centered
    VGroup -- build hook/title cards from this, never from hand-placed Text."""
    if max_width is None:
        max_width = config.frame_width - 1.6
    group = VGroup()
    if kicker:
        group.add(Text(kicker, font_size=24, color=ACCENT, weight=BOLD, font=FONT))
    head = Text(headline, font_size=52, color=INK, weight=BOLD, font=FONT)
    if head.width > max_width:
        head.scale_to_fit_width(max_width)
    group.add(head)
    if subtitle:
        sub = Text(subtitle, font_size=28, color=MUTED, font=FONT)
        if sub.width > max_width:
            sub.scale_to_fit_width(max_width)
        group.add(sub)
    group.arrange(DOWN, buff=0.35)
    return group.move_to(ORIGIN)


def make_network(layer_sizes, node_radius=0.2, width=9.0, height=4.4,
                 node_color=ALT, edge_color=MUTED):
    """Deterministic layered node-and-edge network (neural nets, graphs, pipelines).

    layer_sizes: nodes per layer, e.g. [3, 4, 4, 2]. Nodes are evenly spaced in one column per
    layer and centered vertically; every node wires to every node in the next layer. The whole
    graph is fit inside (width, height) and centered, so it can never cram into one side of the
    frame. Returns a VGroup with .layers (list of per-layer node VGroups), .edges (VGroup of
    Lines) and .nodes (flat VGroup). Reveal it LAYER BY LAYER across beats (Create each column
    with the edges feeding it) -- never Create the whole graph at once, which reads as a tangle."""
    n_layers = len(layer_sizes)
    xs = [0.0] if n_layers == 1 else [
        -width / 2 + i * width / (n_layers - 1) for i in range(n_layers)
    ]
    layers = []
    for li, count in enumerate(layer_sizes):
        ys = [0.0] if count == 1 else [
            height / 2 - j * height / (count - 1) for j in range(count)
        ]
        column = VGroup(*[
            Circle(radius=node_radius, stroke_color=node_color, stroke_width=2.5,
                   fill_color=PANEL, fill_opacity=1.0).move_to([xs[li], y, 0])
            for y in ys
        ])
        layers.append(column)
    edges = VGroup()
    for left, right in zip(layers, layers[1:]):
        for a in left:
            for b in right:
                edges.add(Line(a.get_center(), b.get_center(),
                               color=edge_color, stroke_width=1.4))
    nodes = VGroup(*[node for column in layers for node in column])
    network = VGroup(edges, nodes)
    if network.width > width:
        network.scale_to_fit_width(width)
    if network.height > height:
        network.scale_to_fit_height(height)
    network.move_to(ORIGIN)
    network.layers, network.edges, network.nodes = layers, edges, nodes
    return network
