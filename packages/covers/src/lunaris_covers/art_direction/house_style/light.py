"""The LIGHT-theme rendition of the house style (dual-theme covers) — one definition, three shapes.

The base cover is DARK (every preset renders on a near-black/graphite ground); the light variant is
the SAME cover in a daylight palette, shown in the app's dark theme so the cover contrasts with the
page chrome. These functions are tightly-coupled siblings: they interpolate the one per-preset
palette below, so the thing produced (an edit re-theme, or a native light render) and the thing
judged (the light QA rubric) can never drift into two definitions of the light look.

The palette is per-preset: the GENERAL preset uses the operator's Azure theme VERBATIM
(general-preset template fidelity — paraphrasing it is what made covers diverge from the reference
look); the editorial trio keeps the original ivory ground with the amber accent. Every palette
keeps the no-text discipline.
"""

from lunaris_runtime.schema import CoverStylePreset

from .general_prompt import GENERAL_DARK_THEME, GENERAL_LIGHT_THEME
from .house_style import EDITORIAL_PRESETS

# GENERAL light mode: the operator's Azure theme block, verbatim, plus the no-text tail the theme
# block itself doesn't restate.
_AZURE_LIGHT_PALETTE = (
    f"{GENERAL_LIGHT_THEME}\n\nNO text, letters, numerals, logos or watermarks anywhere."
)

# Editorial light mode (nocturne/blueprint/aurora): the original ivory + amber daylight look.
_AMBER_LIGHT_PALETTE = (
    "Use a LIGHT, daylight palette: a bright near-white or pale warm ivory ground in place of the "
    "near-black night sky, with the single warm amber accent kept as the one saturated focal note. "
    "Keep the matte, editorial, flat-illustration finish — never photoreal, glossy or clip-art — a "
    "single focal subject with generous negative space, and NO text, letters, numerals or logos."
)


def _light_palette(preset: CoverStylePreset) -> str:
    """The light-mode palette for ``preset`` — azure for GENERAL (and any unknown preset, matching
    ``house_style``'s GENERAL fallback), amber for the editorial family (one membership source)."""
    if preset in EDITORIAL_PRESETS:
        return _AMBER_LIGHT_PALETTE
    return _AZURE_LIGHT_PALETTE


def light_retheme_instruction(preset: CoverStylePreset) -> str:
    """The image-EDIT instruction to re-theme a DARK cover render into its light-theme twin.

    Preserves the exact composition, subject, shapes and layout of the supplied image — only the
    palette and value structure flip from night to day, per ``preset``'s light palette.
    """
    return (
        "Re-theme THIS image into its light-mode twin. Preserve the exact composition, subject, "
        "shapes, line work and negative space — change ONLY the palette and value structure. "
        f"{_light_palette(preset)}"
    )


def native_light_prompt(dark_prompt: str, preset: CoverStylePreset) -> str:
    """The full image prompt for a NATIVE light render, derived from the passing dark prompt.

    Used only when the edit-based re-theme fails the vision-QA bar. For the GENERAL preset the dark
    prompt is the operator's full template with the dark COLOR THEME embedded — appending a light
    directive would contradict it — so the dark theme block is SWAPPED for the light one, keeping
    every other field of the passing prompt intact (same subject, same composition spec). The
    editorial prose prompts carry no embedded theme block, so they keep the original behavior: the
    light directive is appended.
    """
    if preset in EDITORIAL_PRESETS:
        return f"{dark_prompt}\n\nCompose this cover for LIGHT MODE. {_AMBER_LIGHT_PALETTE}"
    if GENERAL_DARK_THEME in dark_prompt:
        return dark_prompt.replace(GENERAL_DARK_THEME, GENERAL_LIGHT_THEME)
    # A general prompt without the verbatim dark block (defensive — should not happen): fall back
    # to the append shape so a light render is still attempted rather than skipped.
    return f"{dark_prompt}\n\nCompose this cover for LIGHT MODE. {_AZURE_LIGHT_PALETTE}"


def light_style_block(preset: CoverStylePreset) -> str:
    """The house-style block the LIGHT variant is JUDGED against (the light vision-QA rubric).

    The dark rubric requires a dark ground, which a correct light cover would violate — so the
    light variant is checked against this block instead. It is the same per-preset palette the
    re-theme instruction and native rebuild use, so the thing produced and the thing judged
    can't drift.
    """
    return (
        "LIGHT-THEME COVER — the light-mode twin of the course's dark cover.\n"
        f"{_light_palette(preset)}"
    )
