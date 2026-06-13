# Visual Archetype Taxonomy

This taxonomy is what makes the pipeline work for ANY topic. The planner selects from
these forms; it never invents free-form visuals. Constraining the generative space to
forms with known-good implementations is the single biggest quality lever.

## Selection heuristics

Ask of the scene's narration: what is the *shape* of the claim?

| Claim shape | Archetype |
|---|---|
| "A differs from B" / "A vs B" | comparison/contrast |
| "X causes Y" / "first this, then that" / algorithm steps | process/flow |
| "X is made of parts" / "zoom into X" | hierarchy/decomposition |
| "over time..." / historical narrative / stages | timeline/sequence |
| "where" / geographic or anatomical | spatial/map |
| "how much" / "how fast it grows" / magnitudes | quantity/data |
| abstract concept with no native visual | concrete metaphor |

A scene may compose two (e.g., comparison + quantity = side-by-side bars). More than
two means the scene is overloaded — split it.

## Archetype implementation notes (Manim CE, no LaTeX)

### comparison/contrast
Split screen with `DashedLine` divider; one labeled subject per side, or a 2-column
trade-off grid (rows = dimensions, color-code cells GREEN/DANGER for favorable/
unfavorable). Keep row text ≤ 2 short lines. Validated layout: label column at left
edge, two content columns, thin separator `Line` per row, `LaggedStart` the rows in.

### process/flow
Pointer-driven step-through: highlight current element (stroke color/width), dim
eliminated/past elements (`set_opacity(0.15)`), maintain a running text log in a
corner (each entry `next_to` the previous, `aligned_edge=LEFT`). For state machines:
rounded-rect nodes + `Arrow` edges, light up the active path. Algorithm walkthroughs:
array/structure stays fixed, pointers and opacity carry the story.

### hierarchy/decomposition
Start whole → `Indicate` a part → scale/translate it into focus (or draw a zoom inset
box with `DashedLine` connector) → annotate internals. Always show the connector
between whole and detail; an unanchored detail panel reads as a new diagram.

### timeline/sequence
Horizontal baseline `Line` with tick marks + `Text` date labels; event cards
(`RoundedRectangle` + text) alternate above/below the line to avoid collisions.
Animate left-to-right with `LaggedStart`. Camera pans are unnecessary at ≤7 events;
beyond that, split scenes.

### spatial/map
Simplified procedural regions: `Polygon` blobs with labels, not real cartography —
`round_corners(0.2)` makes blobs read as coastline. Tag the map "schematic" on
screen. For labeled point sets (cities, sites): store a per-point label direction in
the data and choose it away from each point's nearest neighbors (P8); dense clusters
are the most QA-iteration-hungry layout in the whole system. If precision matters,
state in the contract that a static map asset is required and degrade to schematic
("region A / region B") rather than drawing a wrong map. Hedge or omit any per-point
date/figure that Stage 0 didn't ground — an unlabeled dot is honest, a guessed year
is not.

### quantity/data
Bar charts: rectangles grown with `GrowFromEdge(bar, DOWN)` from an explicit baseline
`Line` that MUST span all bars. Value labels `next_to(bar, UP)`. Scale honestly —
linear unless the contract says otherwise, and if linear scale makes small values
invisible, make that the pedagogical beat: say so on screen, then add a labeled
"zoom xN" inset (verify the inset's tallest bar fits the box: h = val/max * scale * N
must be < box height BEFORE choosing N). Hand-rolled curves: build point lists and
`VMobject().set_points_smoothly(points)` — never `Axes` (LaTeX) or `FunctionGraph`
when a custom domain mapping is needed.

### concrete metaphor
Highest risk, highest reward. Only use when the metaphor structurally maps to the
mechanism (winding a signal around a circle ↔ Fourier; spotlight ↔ attention). Build
from primitives like any other asset. If no structural metaphor exists, fall back to
process/flow with good annotation — a forced metaphor is worse than a plain diagram.

## Asset strategy ladder (for non-procedural subjects)

1. **Tier a — procedural vector composition** (default, always try first): turbines,
   panels, machines, icons from `Polygon`/`Circle`/`Rectangle`/`Line`. Validated:
   reads as designed motion-graphics, zero dependencies.
2. **Tier b — provided asset library**: if the harness/user supplies SVGs or PNGs,
   place with `SVGMobject`/`ImageMobject`; keep one consistent style family.
3. **Tier c — generated images**: last resort; breaks cross-scene visual consistency.
   Prefer degrading to schematic tier-a representation instead.
