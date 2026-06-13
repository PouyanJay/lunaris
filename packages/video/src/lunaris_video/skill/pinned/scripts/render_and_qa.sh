#!/usr/bin/env bash
# render_and_qa.sh — Gate A (render) + QA frame extraction for Gate B.
#
# Usage:
#   ./render_and_qa.sh <scenes.py> <SceneName1> [SceneName2 ...]
#
# Renders each scene at 720p30, reports per-scene pass/fail with log tails on
# failure, and extracts QA frames at 30/60/90% of each scene's duration into ./qa/.
# Exit code = number of failed scenes. The agent must then VIEW every qa/*.png
# (Gate B) before assembly — this script cannot look at images; the agent can.
set -uo pipefail

FILE="${1:?usage: render_and_qa.sh <scenes.py> <Scene...>}"; shift
SCENES=("$@")
[ ${#SCENES[@]} -gt 0 ] || { echo "no scenes given"; exit 64; }

STEM="$(basename "$FILE" .py)"
OUTDIR="media/videos/$STEM/720p30"
mkdir -p qa
fails=0

for s in "${SCENES[@]}"; do
  if timeout 900 manim -qm --disable_caching "$FILE" "$s" > "/tmp/render_$s.log" 2>&1; then
    echo "GATE-A PASS  $s"
  else
    echo "GATE-A FAIL  $s  — log tail:"
    tail -15 "/tmp/render_$s.log" | sed 's/^/    /'
    fails=$((fails + 1))
    continue
  fi

  mp4="$OUTDIR/$s.mp4"
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$mp4")
  for frac in 0.3 0.6 0.9; do
    ts=$(awk "BEGIN{printf \"%.3f\", $d * $frac}")
    ffmpeg -y -v error -ss "$ts" -i "$mp4" -frames:v 1 "qa/${s}_${frac}.png"
  done
  echo "         frames: qa/${s}_{0.3,0.6,0.9}.png  (duration ${d}s)"
done

echo
if [ "$fails" -eq 0 ]; then
  echo "Gate A clean. NEXT: view every qa/*.png with vision (Gate B checklist in"
  echo "references/qa-gates.md) before assembling."
else
  echo "$fails scene(s) failed Gate A. Fix and re-run for those scenes only."
fi
exit "$fails"
