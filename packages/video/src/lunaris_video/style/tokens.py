from dataclasses import dataclass


@dataclass(frozen=True)
class VideoStyleTokens:
    """The nine values the skill's ``style_tokens.py`` parameterizes a video with.

    Color fields mirror the skill's token names (BG/INK/…); ``alt`` and ``panel`` are used by
    the validated helpers but are not part of the contract's ``global_style`` (which carries
    only the spec's six colors + font).
    """

    background: str
    ink: str
    muted: str
    accent: str
    danger: str
    success: str
    panel: str
    alt: str
    font: str
