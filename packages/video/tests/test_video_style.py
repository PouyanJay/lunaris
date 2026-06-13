"""Video style tests: the contract's global_style comes from the enterprise-ui token map, and
the generated style_tokens.py is the pinned skill asset with ONLY token values swapped —
helpers byte-identical (principle 4: tokens flow one direction, never forked helpers)."""

from lunaris_video.skill import read_skill_asset
from lunaris_video.style import (
    ENTERPRISE_DARK_TOKENS,
    render_style_tokens_source,
    video_global_style,
)

_COLOR_TOKEN_NAMES = {"BG", "INK", "MUTED", "ACCENT", "DANGER", "GREEN", "PANEL", "ALT"}


def test_video_global_style_delegates_to_the_enterprise_dark_tokens() -> None:
    # Arrange / Act
    style = video_global_style()

    # Assert — delegation, not literals: the hex values themselves are pinned to index.css by
    # tests/video/test_style_token_drift.py; this test guards the field wiring.
    assert style.background == ENTERPRISE_DARK_TOKENS.background
    assert style.primary_text == ENTERPRISE_DARK_TOKENS.ink
    assert style.muted == ENTERPRISE_DARK_TOKENS.muted
    assert style.accent == ENTERPRISE_DARK_TOKENS.accent
    assert style.danger == ENTERPRISE_DARK_TOKENS.danger
    assert style.success == ENTERPRISE_DARK_TOKENS.success
    assert style.font == ENTERPRISE_DARK_TOKENS.font


def test_rendered_style_tokens_swaps_only_color_token_lines() -> None:
    # Arrange
    pinned = read_skill_asset("assets/style_tokens.py").splitlines()

    # Act
    generated = render_style_tokens_source().splitlines()

    # Assert — same line count, and every differing line is one of the color tokens; the
    # validated helpers below the token block are byte-identical. FONT keeps the skill default
    # (render environments are guaranteed DejaVu, not the web font), so its line is unchanged.
    assert len(generated) == len(pinned)
    differing = [g.split()[0] for p, g in zip(pinned, generated, strict=True) if p != g]
    assert set(differing) == _COLOR_TOKEN_NAMES
    font_lines = [g for g in generated if g.startswith("FONT")]
    assert font_lines == [p for p in pinned if p.startswith("FONT")]


def test_rendered_style_tokens_carry_the_video_hex_values() -> None:
    # Arrange / Act
    source = render_style_tokens_source()

    # Assert
    assert f'BG      = "{ENTERPRISE_DARK_TOKENS.background}"' in source
    assert f'ACCENT  = "{ENTERPRISE_DARK_TOKENS.accent}"' in source
    assert f'ALT     = "{ENTERPRISE_DARK_TOKENS.alt}"' in source


def test_rendered_style_tokens_source_is_valid_python() -> None:
    # Arrange / Act / Assert — syntax-check only: importing it needs manim, compiling does not.
    compile(render_style_tokens_source(), "style_tokens.py", "exec")
