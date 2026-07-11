"""The LIGHT-theme rendition of the house style (dual-theme covers) — one definition, three shapes.

The base cover is DARK (every preset renders on a near-black/graphite ground); the light variant is
the SAME cover in a daylight palette, shown in the app's dark theme so the cover contrasts with the
page chrome. These three functions are tightly-coupled siblings: all three interpolate the one
per-preset palette below, so the thing produced (an edit re-theme, or a native light render) and the
thing judged (the light QA rubric) can never drift into two definitions of the light look.

The palette is per-preset (cover-general-preset): the GENERAL preset's light twin is a clean white
ground with AZURE BLUE accents (the operator's light-mode theme); the editorial trio keeps the
original ivory ground with the amber accent. Every palette keeps the no-text discipline.
"""

from lunaris_runtime.schema import CoverStylePreset

# GENERAL light mode (the operator's Azure theme): white/pale ground, azure-blue accent family.
_AZURE_LIGHT_PALETTE = (
    "Use a LIGHT, daylight palette: a clean white, soft ivory or very pale cool-gray ground in "
    "place of the dark graphite, with AZURE BLUE as the dominant accent (azure, clear medium blue, "
    "navy, slate blue, pale sky blue, cool silver, soft neutral gray) applied to the important "
    "components, directional paths and focal highlights. Keep most surfaces white or very light "
    "with subtle blue-gray shadows, and keep the premium editorial-infographic + refined-3D "
    "finish. "
    "Avoid large areas of dark navy, excessive cyan, neon glow, purple accents, and a flat sterile "
    "white background without depth. NO text, letters, numerals or logos."
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
    ``house_style``'s GENERAL fallback), amber for the editorial trio."""
    if preset in (CoverStylePreset.NOCTURNE, CoverStylePreset.BLUEPRINT, CoverStylePreset.AURORA):
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


def light_native_directive(preset: CoverStylePreset) -> str:
    """The suffix appended to a fresh art-direction prompt to compose a NATIVE light cover.

    Used only when the edit-based re-theme fails the vision-QA bar — the cover is then art-directed
    natively for a bright ground (same subject + preset, its own composition) rather than shipped
    as a washed-out edit. Same light look as ``light_retheme_instruction``, as a directive.
    """
    return f"Compose this cover for LIGHT MODE. {_light_palette(preset)}"


def light_style_block(preset: CoverStylePreset) -> str:
    """The house-style block the LIGHT variant is JUDGED against (the light vision-QA rubric).

    The dark rubric requires a dark ground, which a correct light cover would violate — so the
    light variant is checked against this block instead. It is the same per-preset palette the
    re-theme instruction and native directive use, so the thing produced and the thing judged
    can't drift.
    """
    return (
        "LIGHT-THEME COVER — the light-mode twin of the course's dark cover.\n"
        f"{_light_palette(preset)}"
    )
