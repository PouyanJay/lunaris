from lunaris_video.schemas import GlobalStyle
from lunaris_video.style.enterprise_dark import ENTERPRISE_DARK_TOKENS


def video_global_style() -> GlobalStyle:
    """The injected ``global_style`` for every contract — the planner never chooses style.

    Principle 4: tokens flow product → video, one direction. The PLAN node overrides whatever
    a model might emit with this value, so all videos of a course (and the product around them)
    share one palette by construction.
    """
    return GlobalStyle(
        background=ENTERPRISE_DARK_TOKENS.background,
        primary_text=ENTERPRISE_DARK_TOKENS.ink,
        muted=ENTERPRISE_DARK_TOKENS.muted,
        accent=ENTERPRISE_DARK_TOKENS.accent,
        danger=ENTERPRISE_DARK_TOKENS.danger,
        success=ENTERPRISE_DARK_TOKENS.success,
        font=ENTERPRISE_DARK_TOKENS.font,
    )
