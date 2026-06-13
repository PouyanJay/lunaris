# scene_contracts.json Schema

The contract file is the pipeline's central artifact: the planner writes it, the
coding stage implements it, the gates audit against it, and a course-builder harness
consumes it (to regenerate, re-style, translate, or attach TTS). It must be valid
JSON and complete BEFORE any code is written.

```jsonc
{
  "topic": "string - the user's topic, verbatim or lightly normalized",
  "audience": "string - who this is for and what they're assumed to know",
  "visual_archetypes_used": ["list of archetype names actually used"],
  "asset_strategy": "tier-a procedural | tier-b library | mixed (state which scenes)",
  "global_style": {
    "background": "#0E1116",        // override with harness/user design system
    "primary_text": "#E6EDF3",
    "muted": "#5B6470",
    "accent": "#FBBF24",
    "danger": "#F87171",
    "success": "#34D399",
    "font": "DejaVu Sans"           // must exist in render environment
  },
  "voice": {                         // optional - enables narrated output
    "provider": "elevenlabs",
    "voice_id": "<voice id>",        // ONE voice per course for consistency
    "model": "eleven_multilingual_v2"
  },
  "scenes": [
    {
      "id": "S1_problem",            // becomes the Scene class name: S1Problem
      "archetype": "process/flow",   // exactly one primary; compose at most two
      "narration": "string - full spoken script for this scene (concatenation of
                    beat narrations; kept for factual-gate auditing and search)",
      "objects": ["semantic object list - what must exist on screen"],
      "beats": [                     // BEAT OBJECTS - each owns its narration
        {
          "id": "b1",
          "action": "what happens visually during this beat",
          "narration": "the exact sentence(s) spoken DURING this visual action;
                        empty string for silent/pure-visual beats",
          "min_visual_s": 1.5        // floor so fast speech can't rush a visual
        }
      ],
      "sources": ["grounded claims this scene relies on, with source name + figures,
                   OR the literal string 'framing only - no empirical claims'"],
      "duration_s": 18               // TARGET only; actual duration comes from
                                     // timing.json once narration is resolved
    }
  ],
  "verifier_gates": [
    "render_success_per_scene",
    "frame_visual_qa",
    "narration_claim_check_vs_sources"
  ]
}
```

## Field rules

- **id**: `S<N>_<slug>`. The Manim class name is the CamelCase of this id. Files,
  logs, QA frames, and per-scene MP4s all key off it.
- **narration**: write for the ear (short sentences, present tense). Word count ≈
  duration_s × 2.4 words/sec. This field is the single source of truth for claims —
  on-screen text must agree with it.
- **beats**: 3–6 per scene, granular enough that a coder who has never seen the
  topic could implement the scene. Each beat is an object owning its `narration`
  segment — write segments as self-contained clauses (per-beat TTS joins them with
  short pauses; a sentence split across beats sounds broken). Silent beats are
  legitimate pacing: `"narration": ""` + explicit `min_visual_s`. Each beat's
  `action` should be implementable with the building blocks in `manim-patterns.md`.
  The narration-sync pipeline (see `narration-sync.md`) turns these into timing.
- **sources**: non-empty for every scene. The factual gate diffs narration +
  on-screen numbers against this field; an empty/vague sources field on a scene with
  numbers is itself a gate failure.
- **global_style**: when invoked from a course builder, populate from the project's
  design tokens. All scenes of one course must share one global_style.

## Course-builder integration notes

- One contract file per lesson/module video; the harness can batch many.
- The contract is regeneration-stable: re-running Stage 2+ on an unchanged contract
  should produce an equivalent video, so harness-level caching can key on a hash of
  the contract.
- For localization, translate `narration` and on-screen `Text` strings only;
  archetypes, beats, and layout survive translation.
