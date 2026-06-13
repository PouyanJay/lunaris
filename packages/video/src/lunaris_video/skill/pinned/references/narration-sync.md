# Narration & Sync (audio-first)

How to add a synchronized voiceover (ElevenLabs or any TTS) such that the narration
always describes what is on screen at that moment.

## The core principle: audio drives video, never the reverse

Do NOT render the video and then try to fit narration to it — that produces drift,
stretched audio, and dead air. This pipeline controls every animation duration, so
invert the dependency:

```
contracts (beat-level narration)
        │
        ▼
[2.5a SYNTHESIZE]  per-beat TTS clips ──► measured durations
        │
        ▼
[2.5b TIMING]      timing.json  (per scene, per beat: audio_s, anim_s, pad_s)
        │
        ▼
[2 CODE]           scenes read timing.json; run_time/wait come from the manifest
        │
        ▼
[3 RENDER]         video segments are EXACTLY as long as their narration
        │
        ▼
[2.5c MIX]         beat clips + computed silences ──► <SceneName>.wav
        │
        ▼
[4 ASSEMBLE]       assemble.sh auto-muxes <SceneName>.wav onto <SceneName>.mp4
```

Sync is deterministic by construction: each beat's animation window is defined as
`max(audio_duration + pad, min_visual_time)`, so the voice can never outrun or lag
the visuals. No post-hoc alignment exists to drift.

## Contract requirements (see contract-schema.md)

Beats must be objects, each owning its narration:

```jsonc
"beats": [
  { "id": "b1", "action": "array fades in with target card",
    "narration": "You have a sorted list and you want to find one number: 23.",
    "min_visual_s": 1.5 },
  { "id": "b2", "action": "cursor steps cells 0..5, counter increments",
    "narration": "The obvious approach is to scan from the left, one element at a time.",
    "min_visual_s": 3.0 }
]
```

Rules that make sync feel right:
- One narration segment per beat; a beat with no speech gets `"narration": ""` and
  an explicit `min_visual_s` (pure-visual beats are fine — silence is pacing).
- Write narration segments to be self-contained clauses; per-beat synthesis joins
  them with brief pauses, so mid-sentence beat boundaries sound broken.
- `min_visual_s` is the floor for visually complex beats — never let a fast sentence
  rush an animation that needs time to read.

## ElevenLabs specifics

Use the TTS API (NOT the conversational "agents" product — that is for interactive
two-way voice, not baked narration). Auth via `ELEVENLABS_API_KEY` env var. The API
evolves; verify current endpoints/models in the ElevenLabs docs if calls fail.

- Endpoint: `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`
  with header `xi-api-key`, JSON body `{text, model_id, voice_settings}`.
- **Prosody continuity across per-beat clips**: pass `previous_text` / `next_text`
  in each request (the neighboring beats' narration). This is what keeps nine
  separate clips sounding like one continuous take — do not skip it.
- Model choice: `eleven_multilingual_v2` for final quality; flash/turbo variants for
  cheap iteration drafts. Keep one `voice_id` per course (consistency across lessons).
- Timestamp variant: `POST .../v1/text-to-speech/{voice_id}/with-timestamps` returns
  base64 audio + character-level alignment. Use it for the scene-level synthesis
  strategy below; per-beat clips don't need it.

Two synthesis strategies, in order of preference:
1. **Per-beat clips (default).** One request per beat with previous/next text for
   continuity. Robust, trivially measurable (ffprobe), beat-granular retries.
2. **Per-scene single take + timestamps.** Best prosody; locate each beat's text in
   the character alignment to derive beat boundaries. Use when per-beat output
   sounds choppy despite continuity hints. More parsing, same timing.json output.

## The timing manifest

`scripts/narration.py` produces `timing.json`:

```jsonc
{
  "S1_problem": {
    "beats": [
      {"id": "b1", "audio_s": 3.42, "anim_s": 3.42, "audio": "audio/S1_problem_b1.mp3"},
      {"id": "b2", "audio_s": 5.10, "anim_s": 5.10, "audio": "audio/S1_problem_b2.mp3"}
    ],
    "total_s": 8.52
  }
}
```

`anim_s = max(audio_s + pad, min_visual_s)`; when `anim_s > audio_s`, the mix step
inserts trailing silence so audio and video stay equal length per beat.

## Consuming the manifest in scene code

```python
import json
TIMING = json.load(open("timing.json"))

class S1Problem(Scene):
    def construct(self):
        T = {b["id"]: b["anim_s"] for b in TIMING["S1_problem"]["beats"]}
        self.play(FadeIn(title), run_time=min(0.8, T["b1"]))
        self.wait(max(0, T["b1"] - 0.8))          # beat window = its narration
        ...
```

Pattern: each beat's animations + waits must sum to exactly `anim_s` for that beat.
Put a helper at the top of the scene file:

```python
def beat(scene, anims_with_times, total):
    used = 0.0
    for anim, rt in anims_with_times:
        scene.play(anim, run_time=rt); used += rt
    scene.wait(max(0.05, total - used))
```

## No-API fallback: estimate-then-refine

The pipeline must run without TTS access (no key, no network). `narration.py
estimate` writes timing.json from a words-per-minute model (default 150 wpm ≈ 2.5
words/sec + 0.35s inter-beat pause). The whole pipeline runs on estimates; when TTS
becomes available, run `synthesize`, which overwrites timing.json with measured
durations, then re-render (scene-granular, cheap) and re-mix. Never block delivery
on TTS availability — deliver the estimated-timing video plus narration text, and
note it is voice-ready.

## Gate D — sync gate (run after mux)

For each beat: extract the frame at the beat's audio MIDPOINT from the muxed scene

```bash
# midpoint of beat k = sum(anim_s of beats < k) + anim_s[k]/2
ffmpeg -ss <midpoint> -i SceneName_narrated.mp4 -frames:v 1 sync_<scene>_<beat>.png
```

and LOOK at it next to the beat's narration text. The check is semantic: does the
frame show what the words describe? "the right half is eliminated" must show a
dimmed right half AT THAT INSTANT, not two seconds later. Common failures:
- narration references a label/value that hasn't faded in yet → move the FadeIn
  earlier within the beat window
- speech describing motion lands on the post-motion hold → put the motion at the
  start of the beat window, hold at the end
Fix at the beat level, re-render the scene, re-mix, re-check that beat only.

## Audio QA quick checks
- Loudness: normalize beat clips to a common level (`ffmpeg -af loudnorm=I=-16`)
  before mixing if the TTS output varies.
- The final muxed scene must satisfy |video_len − audio_len| < 0.05s (the mix step
  enforces it; verify with ffprobe at Gate D).
