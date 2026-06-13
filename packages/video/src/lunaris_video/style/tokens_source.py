import re

from lunaris_video.skill import read_skill_asset
from lunaris_video.style.enterprise_dark import ENTERPRISE_DARK_TOKENS
from lunaris_video.style.tokens import VideoStyleTokens

_TOKEN_LINE = re.compile(
    r'^(?P<name>BG|INK|MUTED|ACCENT|DANGER|GREEN|PANEL|ALT|FONT)(?P<eq>\s*=\s*)"[^"]*"',
    re.MULTILINE,
)


def render_style_tokens_source(tokens: VideoStyleTokens = ENTERPRISE_DARK_TOKENS) -> str:
    """The ``style_tokens.py`` the pipeline writes next to generated scenes — the pinned asset
    with ONLY token values swapped.

    The skill's instruction is explicit: honor a project design system "by editing the token
    values, not by scattering literals", and never fork the validated helpers. Substituting
    values into the verbatim asset (instead of templating our own copy) keeps the helpers
    byte-identical to the pin — an upstream skill bump flows through automatically.
    """
    values = {
        "BG": tokens.background,
        "INK": tokens.ink,
        "MUTED": tokens.muted,
        "ACCENT": tokens.accent,
        "DANGER": tokens.danger,
        "GREEN": tokens.success,
        "PANEL": tokens.panel,
        "ALT": tokens.alt,
        "FONT": tokens.font,
    }

    def swap(match: re.Match[str]) -> str:
        return f'{match.group("name")}{match.group("eq")}"{values[match.group("name")]}"'

    return _TOKEN_LINE.sub(swap, read_skill_asset("assets/style_tokens.py"))
