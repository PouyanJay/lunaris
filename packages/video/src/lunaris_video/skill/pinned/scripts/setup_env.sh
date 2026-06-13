#!/usr/bin/env bash
# setup_env.sh — one-time per-session environment setup for the explainer-video skill.
# Installs Manim CE + system deps. Idempotent; safe to re-run.
set -uo pipefail

echo "== explainer-video env setup =="

if python3 -c "import manim" 2>/dev/null; then
  echo "manim already installed: $(python3 -c 'import manim; print(manim.__version__)')"
  exit 0
fi

# ffmpeg (usually preinstalled)
if ! command -v ffmpeg >/dev/null 2>&1; then
  apt-get install -y -qq ffmpeg || { echo "FATAL: ffmpeg unavailable"; exit 1; }
fi

# pango/cairo dev headers — required when manimpango has no matching wheel
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq libcairo2-dev libpango1.0-dev pkg-config python3-dev \
  >/dev/null 2>&1 || echo "WARN: apt install failed; trying pip anyway (wheels may suffice)"

pip install manim --break-system-packages -q \
  || pip install manim -q \
  || { echo "FATAL: manim install failed"; exit 1; }

python3 -c "import manim; print('manim', manim.__version__, 'ready')"
echo "NOTE: LaTeX is deliberately NOT installed. Scenes must use Text() only."
