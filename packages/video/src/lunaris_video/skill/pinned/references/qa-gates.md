# Verifier Gates

Three gates, in order. Gate B is the load-bearing one — in validated runs, 100% of
defects were spatial layout issues invisible to the render gate.

## Gate A — Render gate

Render each scene independently:
```bash
manim -qm --disable_caching scenes.py <SceneName> > /tmp/<SceneName>.log 2>&1
```
On failure: read the last ~15 log lines, identify the API misuse, fix with a targeted
edit, re-render THAT scene only. Two consecutive failures on the same scene → re-read
`manim-patterns.md`; the error is almost certainly a catalogued pitfall or an off-list
API call. Never proceed to Gate B with any scene failing.

## Gate B — Visual QA gate (mandatory; do not rationalize skipping it)

Logically-correct code routinely produces visually-broken output. Extract frames at
multiple timestamps — defects appear and disappear as the scene animates, so a single
frame is insufficient (a validated defect was only visible late in its scene):

```bash
d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 $f.mp4)
for frac in 0.3 0.6 0.9; do
  ffmpeg -y -v error -ss $(echo "$d*$frac" | bc) -i $f.mp4 -frames:v 1 qa_${f}_${frac}.png
done
```

Then actually LOOK at every frame with vision and check:

- [ ] Nothing clipped at frame edges; safe margin ≈ 0.4 units all around
- [ ] No text overlapping text; no text overlapping shapes it doesn't belong to
- [ ] Labels visually attached to the object they describe (P2)
- [ ] Rotating/orbiting parts attached at their pivot (P1)
- [ ] All content inside its container box at ALL timestamps (P3)
- [ ] Axes/baselines span every element they support (P4)
- [ ] Dimmed/eliminated elements clearly distinguishable from active ones
- [ ] Color semantics consistent across scenes (same entity = same color)
- [ ] Text legible at 720p (≥15pt equivalent; squint test)

Fix → re-render affected scene only → re-extract → re-look. Iterate to clean.

## Gate C — Factual gate (any topic with empirical claims)

Audit BOTH the contract narration and the rendered on-screen text:
1. Every number on screen appears in some scene's `sources` with a named source.
2. Comparative language ("better", "cleaner", "faster", "edges out") is supported by
   the sourced figures, including their ranges/uncertainty.
3. Data-display scenes carry a small on-screen attribution (muted, ~15pt).
4. Claims that could not be grounded are removed or explicitly hedged on screen —
   never let an ungrounded number ride on visual authority.

## Assembly

```bash
printf "file 'S1.mp4'\nfile 'S2.mp4'\n..." > list.txt
ffmpeg -y -v error -f concat -safe 0 -i list.txt -c copy final.mp4
```
`-c copy` works because all scenes share encoder settings; if any scene was rendered
at a different quality flag, re-render it rather than re-encoding the concat.

## Optional — narration mux (Stage 5)

Per scene: synthesize `narration` with available TTS → `S1.wav`. If audio runs longer
than the scene, prefer stretching the scene's terminal `wait` and re-rendering over
speeding audio. Mux:
```bash
ffmpeg -y -i S1.mp4 -i S1.wav -c:v copy -c:a aac -shortest S1_narrated.mp4
```
Then concat narrated scenes as above (re-encode audio at concat if levels differ:
swap `-c copy` for `-c:v copy -c:a aac`).

## Deliverables checklist

- [ ] final MP4 in the output directory
- [ ] scene_contracts.json alongside it
- [ ] generated scenes .py (+ style_tokens.py if separate)
- [ ] report to the user: scene count, duration, defects caught at each gate and
      their fixes (one line each) — this builds calibrated trust in the pipeline
