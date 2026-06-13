---
name: explainer-video
description: Turn any topic into a 3Blue1Brown-style animated explainer video (MP4) via a five-stage pipeline of factual grounding, scene-contract planning, Manim code generation, render plus visual-QA verification, and assembly. Works for ALL topics, whether mathematical (algorithms, physics, statistics), scientific, technical (architecture, networking), or fully general and humanities topics (history, policy comparisons, X-versus-Y questions, how-things-work). Use this skill whenever the user asks for an explainer video, animated explanation, educational video, a video like 3blue1brown, an animated lesson, or to turn a topic, lesson, or module into a video, even if they never say the word video but want an animated or visual walkthrough of a concept. Also use when a course-generation pipeline needs a video artifact for a lesson or module. Produces the full artifact set of scene_contracts.json, generated Manim Python source, per-scene MP4s, QA frames, and the final MP4.
---

# Explainer Video Pipeline

Transform a topic into a short (30–90s per module) animated explainer video with the
visual quality of a hand-crafted educational animation. The pipeline is five stages
with three verifier gates. Every stage emits an inspectable artifact, so a failed run
is debuggable and a partial run is resumable at scene granularity.

```
topic ─► [0 GROUND] ─► [1 PLAN] ─► [2.5 VOICE/TIMING] ─► [2 CODE] ─► [3 RENDER+VERIFY] ─► [4 ASSEMBLE+MUX]
              │              │            │               │                    │
        sources list   scene_contracts  scenes.py    per-scene MP4s        final.mp4
                           .json                     + QA frames           + artifacts
```

**Why scene-granular:** the scene is the unit of caching, retry, and cost control. A
failed scene re-renders alone; never re-roll the whole video for one broken scene.

## Stage 0 — Factual grounding (general topics; skip for pure formal topics)

If the narration will make empirical claims (numbers, rankings, "X is better than Y",
historical facts), gather grounded values FIRST, before planning. Use web search or
provided source documents. Record every key figure with its source. A wrong number in
a beautiful chart is the worst failure mode this pipeline has: it renders perfectly,
looks authoritative, and is silently false. Formal topics (an algorithm's mechanics, a
mathematical identity) self-verify and can skip this stage.

Output: a list of grounded claims that Stage 1 must embed in the contracts.

## Stage 1 — Plan: write scene_contracts.json

Read `references/contract-schema.md` for the exact schema, then write
`scene_contracts.json`. Key decisions made here (this stage sets the quality ceiling —
spend the thinking budget here, not in the code):

1. **Pick 3–5 scenes**, each 15–30 seconds. Standard arc:
   problem/hook → key insight → mechanism step-by-step → consequence/scale → verdict.
2. **Assign each scene a visual archetype** from `references/archetypes.md`. Read that
   file before planning — it is the taxonomy that makes this work for ANY topic, and
   it includes the selection heuristics. Never invent a free-form visual when an
   archetype fits; archetypes have known-good implementations.
3. **Write the narration per scene.** Narration is a contract field, not an
   afterthought — it drives TTS later and is what the factual gate audits.
4. **Attach `sources` per scene** listing which grounded claims (Stage 0) the scene's
   narration relies on. Write "framing only - no empirical claims" when true.
5. **Find the one inspired beat.** Competent-archetype output is the floor; one scene
   should have a move where the visual's *form* carries the argument (example that
   worked: a linear-scale bar chart where clean-energy bars "barely register" — the
   chart's limitation IS the point, then a zoom inset resolves it). If every scene is
   a generic template fill, revise the plan.

## Stage 2 — Code: generate the Manim file

Read `references/manim-patterns.md` BEFORE writing any code — it contains the
known-good patterns and, more importantly, the spatial pitfalls that caused every
defect in validation runs. The non-negotiables, because each one eliminated an entire
failure class:

- **Manim Community Edition** (`manim`), never manimgl.
- **No LaTeX anywhere.** Use `Text()` only — never `MathTex`/`Tex`/`Axes` with
  `include_numbers=True` (Axes numbers secretly invoke LaTeX). This removes the
  largest dependency and a whole hallucination surface. Hand-roll axes from `Line` +
  `Text` (pattern in the reference).
- **Style tokens from `assets/style_tokens.py`.** Copy it next to the scene file and
  import from it. Consistent palette/typography across all scenes of a course is what
  makes output feel designed rather than generated. Honor any user/project design
  system by editing the token values, not by scattering literals.
- One `Scene` subclass per contract scene, named after the contract `id`.
- Every scene ends by fading out all mobjects (clean concat boundaries), except a
  final closing card.
- Procedural vector assets only (tier-a): build turbines, machines, icons from
  primitives. **Any group that will rotate or orbit needs an explicit invisible
  anchor `Dot` at the pivot** — never rotate about `get_center()` of an asymmetric
  group (bounding-box center ≠ pivot; this detached a turbine's blades from its
  nacelle in validation).

## Stage 3 — Render + verify (two gates, both mandatory)

Use `scripts/render_and_qa.sh` (or replicate its steps): render each scene at `-qm`
(720p30) with `--disable_caching`, then extract QA frames.

**Gate A — render gate.** Per-scene render; on exception, read the stack trace, fix,
re-render that scene only. With the no-LaTeX + patterns discipline, expect near-100%
first-attempt success; repeated API errors mean you skipped the patterns reference.

**Gate B — visual QA gate (load-bearing — do not skip).** Logically-correct code
produces visually-broken output, and no stack trace catches it. Extract frames at
~30%, ~60%, and ~90% of each scene's duration and LOOK at every frame with vision.
Check against the full checklist in `references/qa-gates.md`. The defect classes that
actually occurred in validation, all spatial: labels drifting off their anchored
object during Transform; rotation about wrong pivot; content overflowing a container
*later in the scene* (compute max extent vs container BEFORE animating growth);
baselines/axes not spanning all their elements; text overlap. Fix with targeted
edits, re-render only affected scenes, re-extract, re-look. Iterate until clean.

**Gate C — factual gate (general topics).** Diff every number and comparative claim
in the rendered text and narration against Stage 0 sources. On-screen data displays
should carry a small source attribution.

## Stage 2.5 — Voice & timing resolution (when narrated output is wanted)

Read `references/narration-sync.md` BEFORE writing scene code for a narrated video —
it changes how Stage 2 code is written. The principle: **audio drives video, never
the reverse.** Synthesize (or estimate) narration durations first, write them to
`timing.json` via `scripts/narration.py`, and make every scene read its beat
durations from the manifest instead of hardcoding `run_time`/`wait`. Sync is then
deterministic by construction; "the voice explains what's on screen right now" stops
being an alignment problem.

- With ElevenLabs access (`ELEVENLABS_API_KEY`): `narration.py synthesize` — per-beat
  clips with prosody continuity, measured durations.
- Without: `narration.py estimate` — words-per-minute timing so the entire pipeline
  still runs voice-ready; swap in measured timings later and re-render (cheap,
  scene-granular, zero code edits).
- `narration.py mix` builds one `<SceneId>.wav` per scene (clips + computed
  silences); `assemble.sh` auto-muxes any wav whose stem matches a scene MP4.
- After muxing, run **Gate D (sync gate)** from `narration-sync.md`: frame at each
  beat's audio midpoint must show what that beat's words describe.

## Stage 4 — Assemble + deliver

Concat per-scene MP4s with `scripts/assemble.sh` (stream-copy; scenes share encoding.
If per-scene wavs exist, it muxes narration automatically). Deliver ALL artifacts to
the output directory:

1. `<topic_slug>.mp4` — final video (narrated if Stage 2.5 ran)
2. `scene_contracts.json` — the plan (this is what a course-builder harness consumes
   to regenerate, translate, or re-style)
3. `<topic_slug>_scenes.py` — generated Manim source (with `style_tokens.py` if used)
4. `timing.json` + per-beat audio (when Stage 2.5 ran) — the sync manifest a harness
   needs to re-voice or localize without re-planning

## Environment setup

Run `scripts/setup_env.sh` once per session. It installs pango/cairo dev libs and
Manim CE via pip. ffmpeg is usually preinstalled; the script checks. Setup dominates
wall-time; per-scene marginal cost after it is seconds.

## Calibration (from validated runs)

- 4 scenes ≈ 40s video ≈ 720p renders in ~3–6 min total on a basic container.
- Typical defect count at Gate B: 1–3 per video, all spatial, all fixable with one
  `str_replace`-scale edit each.
- If the user's harness passes a design system (colors, fonts), map it into
  `style_tokens.py` values at Stage 2 — everything downstream inherits it.

## Reference map

| When | Read |
|---|---|
| Before Stage 1 planning | `references/archetypes.md` |
| Before Stage 2 coding | `references/manim-patterns.md` |
| Contract field details | `references/contract-schema.md` |
| Running Gates A/B/C | `references/qa-gates.md` |
| Narrated video (TTS, sync, Gate D) | `references/narration-sync.md` |
