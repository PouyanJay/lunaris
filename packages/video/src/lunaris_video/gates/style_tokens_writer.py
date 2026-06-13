from pathlib import Path

from lunaris_video.style import render_style_tokens_source


def ensure_style_tokens(workdir: Path) -> None:
    """Write the generated ``style_tokens.py`` beside the scenes if it is not there yet.

    Idempotent so it can be called per scene without rewriting the file each time; the scenes'
    ``from style_tokens import *`` resolves against this copy.
    """
    tokens_file = workdir / "style_tokens.py"
    if not tokens_file.exists():
        workdir.mkdir(parents=True, exist_ok=True)
        tokens_file.write_text(render_style_tokens_source(), encoding="utf-8")
