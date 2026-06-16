# Manim CE Patterns & Pitfall Catalog

Every pattern here is validated. Every pitfall here actually occurred and was caught
at a verifier gate. Read fully before writing scene code.

## Hard rules

1. `from manim import *`; set `config.background_color` once at module top.
2. **No LaTeX, ever**: no `MathTex`, `Tex`, `Title`, `BraceLabel`, `Axes`/`NumberLine`
   with numbers, or `DecimalNumber`. All text via `Text(...)`. Math notation: write it
   as unicode text ("O(log n)", "2^k", "gCO2/kWh") — at explainer font sizes this is
   indistinguishable and removes the entire LaTeX dependency + failure surface.
3. Import shared tokens/helpers from `style_tokens.py` (copy from skill `assets/`).
4. Stay on the stable core API: Square, Rectangle, RoundedRectangle, Circle, Polygon,
   Line, DashedLine, Arrow, Dot, Text, VGroup, VMobject, SurroundingRectangle, Cross,
   FadeIn/Out, Create, Write, Transform, GrowFromEdge, GrowArrow, Rotate, Indicate,
   Flash, LaggedStart. Anything beyond this list: justify it or don't use it.
5. Render command: `manim -qm --disable_caching <file>.py <SceneName>` (720p30; use
   `-qh` only for final masters if asked).

## Validated building blocks

### Title bar (use on every scene)
```python
def title_bar(text):
    t = Text(text, font_size=33, color=INK, weight=BOLD)
    underline = Line(LEFT, RIGHT, color=ACCENT, stroke_width=3)
    underline.set_width(t.width)
    underline.next_to(t, DOWN, buff=0.12)
    return VGroup(t, underline).to_edge(UP, buff=0.45)
```

### Cell array (algorithms, sequences) — fits 15 cells at cell=0.82, buff=0.07
```python
def make_array(values, cell=0.82, font_size=22):
    cells = VGroup()
    for v in values:
        sq = Square(side_length=cell, stroke_color=MUTED, stroke_width=1.6,
                    fill_color=PANEL, fill_opacity=1.0)
        num = Text(str(v), font_size=font_size, color=INK)
        num.scale_to_fit_width(min(num.width, cell * 0.72))   # 3-digit safety
        cells.add(VGroup(sq, num.move_to(sq)))
    cells.arrange(RIGHT, buff=0.07)
    idx = VGroup(*[Text(str(i), font_size=15, color=MUTED).next_to(c, DOWN, buff=0.18)
                   for i, c in enumerate(cells)])
    return cells, idx
```
Step-through idiom: highlight = `cells[i][0].animate.set_stroke(ACCENT, 3)`;
eliminate = `VGroup(*cells[a:b], *idx[a:b]).animate.set_opacity(0.15)`.

### Hand-rolled axes + smooth curves (replaces Axes/FunctionGraph)
```python
ox, oy, w, h = -5.4, -1.3, 10.8, 2.9
xaxis = Line([ox, oy, 0], [ox + w, oy, 0], color=MUTED, stroke_width=2)
yaxis = Line([ox, oy, 0], [ox, oy + h, 0], color=MUTED, stroke_width=2)
# ticks: short Lines + Text labels at fractional positions along w
def curve_points(f, n=120):   # f: [0,1] -> [0,1]
    return [[ox + (i/n)*w, oy + f(i/n)*h, 0] for i in range(n+1)]
curve = VMobject(stroke_color=ACCENT, stroke_width=4)
curve.set_points_smoothly(curve_points(my_f))
```

### Bar chart with honest-scale zoom inset
Baseline `Line` must span ALL bars (PITFALL 4). Bars:
`Rectangle(...).move_to([x, baseline_y + h/2, 0])`, animate `GrowFromEdge(bar, DOWN)`.
Zoom inset: before choosing zoom factor N, verify
`max_val/chart_max * max_h * N < inset_box_height` (PITFALL 3).

### Procedural assets with a rotation pivot (PITFALL 1 fix baked in)
```python
def make_turbine(scale=1.0):
    ...
    blades = VGroup(*[blade.copy().rotate(i*TAU/3, about_point=ORIGIN) for i in range(3)])
    blades.shift(np.array(hub))                      # shift, NOT move_to
    anchor = Dot(hub, radius=0.001, fill_opacity=0, stroke_opacity=0)
    g = VGroup(tower, nacelle, blades, cap, anchor).scale(scale)
    g.blades, g.hub_anchor = blades, anchor
    return g
# animate: Rotate(t.blades, angle=TAU, about_point=t.hub_anchor.get_center())
```

### Network / layered graph (nodes + edges) — the `make_network` helper
Neural nets, computational graphs, and pipelines are nodes wired together. Never hand-place
node coordinates (the result crams into one side, half-formed — PITFALL 9). Use the helper:
```python
net = make_network([3, 4, 4, 2])          # nodes per layer; fits the frame, centered
# net.layers : list of per-layer node VGroups (columns, left→right)
# net.edges  : VGroup of the connecting Lines (drawn under the nodes)
# net.nodes  : flat VGroup of every node Circle
# reveal LAYER BY LAYER so a beat's words land on the column it names — never all at once:
self.play(Create(net.layers[0]))
for col in net.layers[1:]:
    self.play(Create(col), Create(VGroup(*[e for e in net.edges if _feeds(e, col)])))
```
Simpler and just as clean: `Create(net.edges)` then `LaggedStart(*[Create(c) for c in
net.layers])` if the beats don't need per-column timing. Keep it readable — ≤ ~6 nodes per
layer; summarize a bigger network with a vertical "…" between two representative nodes.

### Scene hygiene
End every non-final scene with `self.play(*[FadeOut(m) for m in self.mobjects])` so
concatenated scenes cut cleanly. Keep one breathing `self.wait(1.5-2.0)` on each
scene's punchline — uniform 0.5s pacing is the tell of generated video.

## Pitfall catalog (each caused a real defect)

**P1 — Rotation about bounding-box center.** `Rotate(group)` defaults to the group's
bbox center, which is NOT the visual pivot for asymmetric groups. Result: turbine
blades detached from nacelle. Fix: invisible anchor `Dot` at the pivot; rotate
`about_point=anchor.get_center()`. Same applies to orbits and clock hands.

**P2 — Labels drifting off transformed objects.** Transforming a shape to a new
size/position while `Transform`-ing its label to a copy positioned relative to the
OLD shape leaves labels floating. Fix: position every new label relative to the NEW
object (`next_to(new_bar, ...)` + `align_to(new_bar, LEFT)`), then Transform.

**P3 — Latent container overflow.** Content that grows during the scene can breach
its container even though the layout looks fine at design time. Compute maximum
extent arithmetically against the container BEFORE animating. Caught: zoom-inset bar
at x20 would exceed inset box; x12 fit.

**P4 — Axis/baseline under-span.** A baseline drawn for the "designed" bars doesn't
cover bars added later or at the end. Derive baseline endpoints from the actual bar
positions: `last_x + bar_width/2 + margin`.

**P5 — Text collision in dense scenes.** Corner logs, tallies, and captions compete
for the bottom band. Assign bands explicitly: log = bottom-left, tally = bottom-right,
caption = bottom-center, and never use more than two per scene.

**P6 — 3+ digit text overflowing fixed cells.** Always
`scale_to_fit_width(min(width, cell*0.72))` on cell text.

**P7 — `move_to` vs `shift` for pivot-rooted groups.** `move_to(p)` places the bbox
center at p; for a group whose local origin is meaningful (blades rooted at ORIGIN),
use `shift(p)` to preserve the origin↔pivot relationship.

**P8 — Label collisions in dense point clusters (maps, scatter).** When labeled
points cluster, uniform label placement (all `UP`) guarantees collisions. Assign a
per-point label direction in the data (UP/DOWN/LEFT/RIGHT) chosen by where that
point's neighbors are NOT. And when Gate B forces a label relocation, re-check the
label's NEW neighbors — fixing one collision routinely creates another one step away
(observed: moving a label DOWN cleared its northern neighbor and grazed its southern
one). Expect map scenes to take one extra QA iteration; budget for it.

**P9 — Hand-placed networks cram into one side.** A "web of nodes wired together" laid
out with ad-hoc coordinates packs the nodes into a corner and Creates the whole tangle at
once, so the narrated unit is never cleanly on screen (the neural-net hook failure). Fix:
`make_network(layer_sizes)` for a frame-fitting, centered layout, and reveal it layer by
layer so each beat's words land on the column it names. Cap on-screen size (≤ ~6 nodes per
layer); summarize a bigger network rather than drawing every unit.

**P10 — Malformed numeric literals.** A number jammed against a name (`2x`, `3pi`) is an
"invalid decimal literal" SyntaxError — the model meant `2 * x`. (Bare `.5` / `5.` parse but
read poorly and invite this mistake.) Fix: always put an operator between a number and a name
(`2 * x`, never `2x`); write decimals with a digit on BOTH sides of the point (`0.5`, `5.0`),
and never put a comma or stray character inside a numeric literal. (Do NOT rely on a tool to
"repair" `.5`/`5.` — those are valid Python; rewriting them deterministically would corrupt
on-screen numbers like `"Step 5."`, so the rule lives here as guidance, not a post-fix.)

**P11 — Unterminated string literals.** The #1 codegen parse failure: a quote opened and never
closed on the same line, or a bare string spanning lines. Fix: straight ASCII quotes only
(`"` or `'`), never smart/curly quotes; CLOSE every quote on the SAME line; write a line break
inside a string as the two characters `\n` (never a real newline mid-string); and build a long
message from adjacent pieces (`"part one " "part two"`), never one line-spanning string.
