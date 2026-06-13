"""Cross-cutting drift pin: the video style tokens ARE the enterprise-ui dark-theme tokens.

Principle 4 (plan): design tokens flow one direction, product → video. This test holds the
package's token map to the web's token block — re-skinning the product without re-mapping the
video tokens turns this red instead of silently shipping off-brand videos. Repo-level because
it spans apps/web and packages/video; collected via ``testpaths``.
"""

from pathlib import Path

from lunaris_video.style import ENTERPRISE_DARK_TOKENS

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOKEN_CSS = _REPO_ROOT / "apps" / "web" / "src" / "index.css"


def test_every_video_color_token_exists_in_the_web_token_block() -> None:
    # Arrange
    css = _TOKEN_CSS.read_text(encoding="utf-8").lower()
    color_tokens = {
        "background": ENTERPRISE_DARK_TOKENS.background,
        "ink": ENTERPRISE_DARK_TOKENS.ink,
        "muted": ENTERPRISE_DARK_TOKENS.muted,
        "accent": ENTERPRISE_DARK_TOKENS.accent,
        "danger": ENTERPRISE_DARK_TOKENS.danger,
        "success": ENTERPRISE_DARK_TOKENS.success,
        "panel": ENTERPRISE_DARK_TOKENS.panel,
        "alt": ENTERPRISE_DARK_TOKENS.alt,
    }

    # Act / Assert — every mapped hex must still be a literal in the web's token source.
    for name, value in color_tokens.items():
        assert value.lower() in css, f"video token {name}={value} no longer in index.css"
