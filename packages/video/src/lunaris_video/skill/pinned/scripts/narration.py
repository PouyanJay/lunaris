#!/usr/bin/env python3
"""
narration.py — audio-first narration pipeline for the explainer-video skill.

Subcommands:
  estimate    contracts.json -> timing.json using a words-per-minute model
              (no network, no key; lets the full pipeline run voice-ready)
  synthesize  contracts.json -> per-beat TTS clips via ElevenLabs + measured
              timing.json (requires ELEVENLABS_API_KEY)
  mix         timing.json -> one <SceneId>.wav per scene (beat clips + computed
              silences), sized to exactly match the scene's animation timeline.
              assemble.sh auto-muxes these by stem name.

Usage:
  python3 narration.py estimate  scene_contracts.json [--wpm 150] [--pause 0.35]
  python3 narration.py synthesize scene_contracts.json --voice-id VOICE \
          [--model eleven_multilingual_v2] [--out audio/]
  python3 narration.py mix timing.json --out audio/
"""
import argparse, base64, json, math, os, subprocess, sys, urllib.request

PAUSE_DEFAULT = 0.35
MIN_BEAT_S = 0.6


def load_contracts(path):
    with open(path) as f:
        c = json.load(f)
    scenes = []
    for sc in c["scenes"]:
        beats = sc.get("beats", [])
        # Back-compat: string beats -> single narration beat from scene narration
        if beats and isinstance(beats[0], str):
            beats = [{"id": "b1", "action": "; ".join(beats),
                      "narration": sc.get("narration", ""), "min_visual_s": 2.0}]
        scenes.append({"id": sc["id"], "beats": beats})
    return scenes


def ffprobe_duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path])
    return float(out.strip())


def write_timing(scenes_timing, path="timing.json"):
    with open(path, "w") as f:
        json.dump(scenes_timing, f, indent=2)
    print(f"wrote {path}")


def cmd_estimate(args):
    wps = args.wpm / 60.0
    timing = {}
    for sc in load_contracts(args.contracts):
        beats, total = [], 0.0
        for b in sc["beats"]:
            words = len(b.get("narration", "").split())
            audio_s = round(words / wps + (args.pause if words else 0.0), 2)
            anim_s = round(max(audio_s, b.get("min_visual_s", MIN_BEAT_S)), 2)
            beats.append({"id": b["id"], "audio_s": audio_s, "anim_s": anim_s,
                          "audio": None, "estimated": True})
            total += anim_s
        timing[sc["id"]] = {"beats": beats, "total_s": round(total, 2)}
    write_timing(timing)


def eleven_tts(text, voice_id, model, api_key, prev_text, next_text):
    body = {"text": text, "model_id": model,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
    if prev_text:
        body["previous_text"] = prev_text
    if next_text:
        body["next_text"] = next_text
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        f"?output_format=mp3_44100_128",
        data=json.dumps(body).encode(),
        headers={"xi-api-key": api_key, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def cmd_synthesize(args):
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        sys.exit("ELEVENLABS_API_KEY not set. Run `estimate` for the no-API path.")
    os.makedirs(args.out, exist_ok=True)
    timing = {}
    for sc in load_contracts(args.contracts):
        beats, total = [], 0.0
        narrs = [b.get("narration", "") for b in sc["beats"]]
        for i, b in enumerate(sc["beats"]):
            text = narrs[i].strip()
            if not text:
                anim_s = round(b.get("min_visual_s", MIN_BEAT_S), 2)
                beats.append({"id": b["id"], "audio_s": 0.0, "anim_s": anim_s,
                              "audio": None})
                total += anim_s
                continue
            audio = eleven_tts(
                text, args.voice_id, args.model, api_key,
                prev_text=" ".join(narrs[max(0, i - 1):i]) or None,
                next_text=" ".join(narrs[i + 1:i + 2]) or None)
            path = os.path.join(args.out, f"{sc['id']}_{b['id']}.mp3")
            with open(path, "wb") as f:
                f.write(audio)
            audio_s = round(ffprobe_duration(path), 2)
            anim_s = round(max(audio_s + args.pad,
                               b.get("min_visual_s", MIN_BEAT_S)), 2)
            beats.append({"id": b["id"], "audio_s": audio_s, "anim_s": anim_s,
                          "audio": path})
            total += anim_s
            print(f"  {sc['id']}/{b['id']}: {audio_s}s audio -> {anim_s}s beat")
        timing[sc["id"]] = {"beats": beats, "total_s": round(total, 2)}
    write_timing(timing)


def class_name(scene_id):
    """Contract id -> Manim class name, same rule as the coding stage:
    S1_problem -> S1Problem."""
    return "".join(p[:1].upper() + p[1:] for p in scene_id.split("_"))


def cmd_mix(args):
    with open(args.timing) as f:
        timing = json.load(f)
    os.makedirs(args.out, exist_ok=True)
    for scene_id, sc in timing.items():
        parts, filt, idx = [], [], 0
        cmd = ["ffmpeg", "-y", "-v", "error"]
        segs = []
        for b in sc["beats"]:
            gap = round(b["anim_s"] - b["audio_s"], 3)
            if b.get("audio"):
                cmd += ["-i", b["audio"]]
                segs.append(("file", idx)); idx += 1
                if gap > 0.01:
                    segs.append(("silence", gap))
            else:
                segs.append(("silence", b["anim_s"]))
        # build filtergraph: silence via anullsrc trims
        graph, labels = [], []
        for j, (kind, v) in enumerate(segs):
            if kind == "file":
                graph.append(f"[{v}:a]aformat=sample_rates=44100:"
                             f"channel_layouts=stereo[a{j}]")
            else:
                graph.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{v}[a{j}]")
            labels.append(f"[a{j}]")
        graph.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[out]")
        wav = os.path.join(args.out, f"{class_name(scene_id)}.wav")
        full = cmd + ["-filter_complex", ";".join(graph), "-map", "[out]", wav]
        subprocess.check_call(full)
        got = ffprobe_duration(wav)
        drift = abs(got - sc["total_s"])
        flag = "OK" if drift < 0.05 else f"DRIFT {drift:.3f}s — investigate"
        print(f"  {class_name(scene_id)}.wav  {got:.2f}s vs timeline {sc['total_s']}s  [{flag}]")
    print(f"\nScene wavs in {args.out}/ — name them next to the scene MP4s and "
          f"assemble.sh will auto-mux by stem.")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("estimate")
    e.add_argument("contracts")
    e.add_argument("--wpm", type=float, default=150)
    e.add_argument("--pause", type=float, default=PAUSE_DEFAULT)
    e.set_defaults(fn=cmd_estimate)

    s = sub.add_parser("synthesize")
    s.add_argument("contracts")
    s.add_argument("--voice-id", required=True)
    s.add_argument("--model", default="eleven_multilingual_v2")
    s.add_argument("--out", default="audio")
    s.add_argument("--pad", type=float, default=0.15)
    s.set_defaults(fn=cmd_synthesize)

    m = sub.add_parser("mix")
    m.add_argument("timing")
    m.add_argument("--out", default="audio")
    m.set_defaults(fn=cmd_mix)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
