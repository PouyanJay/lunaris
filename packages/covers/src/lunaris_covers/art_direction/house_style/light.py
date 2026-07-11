"""The LIGHT-theme rendition of the house style (dual-theme covers) — one definition, three shapes.

The base cover is DARK (every preset is night-sky anchored — see the sibling ``house_style``
module's locked constraint #3); the light variant is the SAME cover in a daylight palette, shown in
the app's dark theme so the cover contrasts with the page chrome. These three functions are
tightly-coupled siblings: all three interpolate the one private ``_LIGHT_PALETTE`` so the thing
produced (an edit re-theme, or a native light render) and the thing judged (the light QA rubric) can
never drift into two definitions of the light look. Each keeps every anti-slop discipline (one
subject, no text, matte editorial finish, a single amber accent) — only the ground flips to bright.
"""

_LIGHT_PALETTE = (
    "Use a LIGHT, daylight palette: a bright near-white or pale warm ivory ground in place of the "
    "near-black night sky, with the single warm amber accent kept as the one saturated focal note. "
    "Keep the matte, editorial, flat-illustration finish — never photoreal, glossy or clip-art — a "
    "single focal subject with generous negative space, and NO text, letters, numerals or logos."
)


def light_retheme_instruction() -> str:
    """The image-EDIT instruction to re-theme a DARK cover render into its light-theme twin.

    Preserves the exact composition, subject, shapes and layout of the supplied image — only the
    value structure flips from night to day. Preset-agnostic: the preset already shaped the dark
    render being edited, so only the palette changes here.
    """
    return (
        "Re-theme THIS image into its light-mode twin. Preserve the exact composition, subject, "
        "shapes, line work and negative space — change ONLY the palette and value structure. "
        f"{_LIGHT_PALETTE}"
    )


def light_native_directive() -> str:
    """The suffix appended to a fresh art-direction prompt to compose a NATIVE light cover.

    Used only when the edit-based re-theme fails the vision-QA bar — the cover is then art-directed
    natively for a bright ground (same subject + preset, its own composition) rather than shipped as
    a washed-out edit. Same light look as ``light_retheme_instruction``, expressed as a directive.
    """
    return f"Compose this cover for LIGHT MODE. {_LIGHT_PALETTE}"


def light_style_block() -> str:
    """The house-style block the LIGHT variant is JUDGED against (the light vision-QA rubric).

    The dark rubric requires a near-black ground (locked constraint #3), which a correct light cover
    would violate — so the light variant is checked against this block instead. It is the same
    ``_LIGHT_PALETTE`` the re-theme instruction and native directive use, so the thing produced and
    the thing judged can't drift.
    """
    return f"LIGHT-THEME COVER — the light-mode twin of the course's dark cover.\n{_LIGHT_PALETTE}"
