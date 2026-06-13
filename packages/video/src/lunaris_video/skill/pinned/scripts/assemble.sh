#!/usr/bin/env bash
# assemble.sh — Stage 4: concat per-scene MP4s into the final video.
#
# Usage:
#   ./assemble.sh <output.mp4> <scene1.mp4> <scene2.mp4> [...]
#
# Scenes must share encoder settings (same -q flag at render) so stream-copy works.
# If a per-scene .wav with the same stem exists next to a scene MP4, it is muxed in
# first (narration), then everything is concatenated.
set -euo pipefail

OUT="${1:?usage: assemble.sh <output.mp4> <scene mp4s...>}"; shift
LIST="$(mktemp)"; trap 'rm -f "$LIST"' EXIT
HAS_AUDIO=0

for f in "$@"; do
  stem="${f%.mp4}"
  if [ -f "$stem.wav" ]; then
    ffmpeg -y -v error -i "$f" -i "$stem.wav" -c:v copy -c:a aac -shortest \
      "${stem}_narrated.mp4"
    printf "file '%s'\n" "$(realpath "${stem}_narrated.mp4")" >> "$LIST"
    HAS_AUDIO=1
  else
    printf "file '%s'\n" "$(realpath "$f")" >> "$LIST"
  fi
done

if [ "$HAS_AUDIO" -eq 1 ]; then
  # mixed/narrated inputs: re-encode audio at concat for level consistency
  ffmpeg -y -v error -f concat -safe 0 -i "$LIST" -c:v copy -c:a aac "$OUT"
else
  ffmpeg -y -v error -f concat -safe 0 -i "$LIST" -c copy "$OUT"
fi

ffprobe -v error -show_entries format=duration,size -of csv=p=0 "$OUT" \
  | awk -F, '{printf "assembled %s: %.1fs, %.1f MB\n", "'"$OUT"'", $1, $2/1048576}'
