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
