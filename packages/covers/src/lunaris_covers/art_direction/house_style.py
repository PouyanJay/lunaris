from dataclasses import dataclass

from lunaris_runtime.schema import CoverStylePreset

# The locked anti-slop constraints EVERY cover obeys, regardless of preset (requirements § House
# style). This is the single source of truth for the discipline — the art director bakes it into the
# image prompt, and the vision-QA gate (T5) rejects any cover that violates it — so the prompt and
# the rubric can never drift into two different definitions of "on brand".
_LOCKED_CONSTRAINTS = (
    "ONE focal subject, with generous negative space — never busy or cluttered.",
    "NO text, letters, numerals, logos or watermarks anywhere in the image "
    "(garbled AI text is the #1 slop tell).",
    "A limited palette anchored to the Lunaris brand: a near-black night-sky ground with a single "
    "warm amber accent; no other saturated colours.",
    "A matte, editorial, flat-illustration finish — never photoreal stock, generic 3D render, or "
    "glossy corporate clip-art.",
    "The subject is DERIVED from the course topic and its concepts — evocative and descriptive, "
    "not a literal or busy depiction of them.",
)

# Per-preset medium/mood. The preset varies the look; it never relaxes a locked constraint above.
_PRESET_DIRECTIVES: dict[CoverStylePreset, str] = {
    CoverStylePreset.NOCTURNE: (
        "Preset NOCTURNE (the house default): a night-sky editorial illustration — a single "
        "luminous motif against deep near-black, faint constellation accents in amber."
    ),
    CoverStylePreset.BLUEPRINT: (
        "Preset BLUEPRINT: a technical schematic / fine line-art drawing in pale amber on deep "
        "near-black, like an elegant engineering blueprint of the subject."
    ),
    CoverStylePreset.AURORA: (
        "Preset AURORA: a soft abstract gradient field on near-black with one restrained amber "
        "motif — atmospheric and calm, a single gesture."
    ),
}


@dataclass(frozen=True)
class HouseStyle:
    """The house-style brief for one preset: the locked constraints plus that preset's medium/mood.

    ``constraints`` are the same for every preset (the anti-slop discipline);
    ``preset_directive`` is the preset-specific medium. Both the art director's prompt and the QA
    rubric read from here so they share one definition of the style.
    """

    constraints: tuple[str, ...]
    preset_directive: str

    def as_prompt_block(self) -> str:
        """The constraints + preset directive rendered as a numbered block for a prompt/rubric."""
        rules = "\n".join(f"{n}. {rule}" for n, rule in enumerate(self.constraints, start=1))
        return f"{self.preset_directive}\n\nNON-NEGOTIABLE CONSTRAINTS:\n{rules}"


def house_style(preset: CoverStylePreset) -> HouseStyle:
    """The locked constraints plus the medium/mood for ``preset``.

    An unknown preset falls back to the house ``NOCTURNE`` directive rather than raising — a cover
    is always designable — while still carrying the full locked constraints.
    """
    directive = _PRESET_DIRECTIVES.get(preset, _PRESET_DIRECTIVES[CoverStylePreset.NOCTURNE])
    return HouseStyle(constraints=_LOCKED_CONSTRAINTS, preset_directive=directive)


# The house LIGHT-theme rendition (dual-theme covers). The base cover is DARK (every preset is
# night-sky anchored — locked constraint #3); the light variant is the SAME cover in a daylight
# palette, shown in the app's dark theme so the cover contrasts with the page chrome. Two shapes,
# ONE definition of the light look so they can't drift: an EDIT instruction that re-themes an
# existing dark render in place (composition preserved), and a NATIVE art-direction suffix appended
# to a fresh prompt when the edit can't pass QA. Both keep every anti-slop discipline (one subject,
# no text, matte editorial finish, a single amber accent) — only the ground flips to bright.
_LIGHT_PALETTE = (
    "Use a LIGHT, daylight palette: a bright near-white or pale warm ivory ground in place of the "
    "near-black night sky, with the single warm amber accent kept as the one saturated focal note. "
    "Keep the matte, editorial, flat-illustration finish — never photoreal, glossy or clip-art — a "
    "single focal subject with generous negative space, and NO text, letters, numerals or logos."
)


def light_retheme_instruction(preset: CoverStylePreset) -> str:
    """The image-EDIT instruction to re-theme a DARK cover render into its light-theme twin.

    Preserves the exact composition, subject, shapes and layout of the supplied image — only the
    value structure flips from night to day. Anchored to the same ``_LIGHT_PALETTE`` the native
    fallback uses so both routes mean the same light look.
    """
    _ = preset  # the preset already shaped the dark render being edited; the palette is shared
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
