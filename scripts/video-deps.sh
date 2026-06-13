#!/usr/bin/env bash
# scripts/video-deps.sh — install the local explainer-video render toolchain.
#
# The render extra (Manim CE) is optional on purpose: hermetic tests and CI never need it.
# This script makes a dev machine render-capable: system libs (cairo/pango/pkg-config via
# Homebrew on macOS — pycairo builds from source against them), the Python extra, and a
# verification pass (manim importable, ffmpeg on PATH).

set -euo pipefail

source "$(dirname "$0")/lib/ui.sh"

ui::section "Video render toolchain"

ui::step 1 3 "System libraries (cairo / pango / pkg-config)"
if [[ "$(uname -s)" == "Darwin" ]]; then
  command -v brew >/dev/null 2>&1 \
    || ui::die "Homebrew is required on macOS" "install it from https://brew.sh"
  for pkg in cairo pango pkgconf; do
    if brew list --versions "$pkg" >/dev/null 2>&1; then
      ui::ok "$pkg"
    else
      ui::info "installing $pkg"
      brew install "$pkg"
      ui::ok "$pkg"
    fi
  done
else
  ui::info "Linux: ensure libcairo2-dev libpango1.0-dev pkg-config are installed (apt)"
fi

ui::step 2 3 "Python render extra (Manim CE)"
uv sync --all-packages --all-extras --quiet
ui::ok "uv sync --all-packages --all-extras"

ui::step 3 3 "Toolchain verification"
manim_version="$(uv run python -c 'import manim; print(manim.__version__)')" \
  || ui::die "manim failed to import" "re-run: uv sync --all-packages --all-extras"
ui::ok "manim"
ui::detail "manim ${manim_version}"
command -v ffmpeg >/dev/null 2>&1 \
  || ui::die "ffmpeg not found on PATH" "brew install ffmpeg (macOS) / apt install ffmpeg"
ui::ok "ffmpeg"
ui::detail "$(ffmpeg -version 2>/dev/null | head -1)"

printf "\n"
ui::ok "video render toolchain ready"
