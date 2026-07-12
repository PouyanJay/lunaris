from dataclasses import dataclass

from lunaris_runtime.schema import CoverStylePreset

# The anti-slop constraints shared by EVERY preset (requirements § House style). This is the part of
# the discipline that never varies: the art director bakes it into the image prompt, and the
# vision-QA gate rejects any cover that violates it — so the prompt and the rubric can never drift
# into two different definitions of "on brand".
_SHARED_CONSTRAINTS = ("No logos or watermarks anywhere in the image.",)

# The EDITORIAL discipline (the original locked constraints) — the nocturne/blueprint/aurora trio:
# one focal subject, a flat matte illustration, a night-sky ground with a single amber accent.
_EDITORIAL_CONSTRAINTS = (
    *_SHARED_CONSTRAINTS,
    "NO text, letters or numerals anywhere in the image (the editorial covers are wordless art; "
    "garbled lettering is the #1 slop tell).",
    "The subject is DERIVED from the course topic and its concepts — evocative and descriptive, "
    "not a literal or busy depiction of them.",
    "ONE focal subject, with generous negative space — never busy or cluttered.",
    "A limited palette anchored to the Lunaris brand: a near-black night-sky ground with a single "
    "warm amber accent; no other saturated colours.",
    "A matte, editorial, flat-illustration finish — never photoreal stock, generic 3D render, or "
    "glossy corporate clip-art.",
)

# The GENERAL discipline (cover-general-preset, distilled from the operator's course-cover prompt
# system): a premium enterprise-learning cover — a modern editorial infographic fused with REFINED
# 3D illustration. Deliberately its own constraint set: the editorial trio forbids 3D and mandates
# a flat finish, which would make every general cover fail its own QA gate.
_GENERAL_CONSTRAINTS = (
    *_SHARED_CONSTRAINTS,
    "The cover CARRIES TYPOGRAPHY (general-cover-typography): the eyebrow label, the stacked "
    "course title with one line accented in amber, the subtitle, three captioned badges, and any "
    "callout "
    "labels are typeset INTO the image, in the left third, never overlapping the artwork. Every "
    "letterform must be crisp, correctly spelled and legible — garbled, invented, misspelled or "
    "duplicated words are the #1 slop tell and are rejected.",
    "Scientifically/technically CORRECT: the image must not depict a misleading relationship, a "
    "wrong structure, or anything a subject-matter expert would call an error — a cover that "
    "misteaches is worse than a plain one.",
    "A LITERAL, technically and anatomically accurate depiction of the course's actual subject "
    "and mechanism — the scene a textbook illustrator would draw (recognizable organs, devices, "
    "systems, structures, processes); never an abstract metaphor, a mood piece, or shapes that "
    "merely 'suggest' the topic.",
    "ONE dominant hero visualization placed toward the center-right, plus two to four SEPARATE, "
    "stand-alone supporting elements arranged around it as a diagram — e.g. a magnified circular "
    "inset revealing internal structure, discrete floating components, a connected flow between "
    "parts — each element its own distinct object with clear spatial separation, readable at "
    "thumbnail size, important elements away from the edges, generous clean negative space "
    "weighted to the left.",
    "A dark, sophisticated ground of near-black, charcoal and deep graphite with the amber family "
    "as the accent (rich amber, golden orange, warm honey, dark bronze, muted copper, warm "
    "ivory), applied selectively to important components — no blue or purple accents, no neon "
    "yellow, no flat pure black without dimensional variation.",
    "A premium enterprise finish: a modern editorial infographic combined with refined 3D "
    "illustration — clean geometry, precise spacing, soft controlled studio lighting, subtle "
    "shadows and ambient occlusion, refined glass / matte metal / ceramic / translucent "
    "materials, subtle dimensional depth. Sharp edges and crisp, high-frequency detail "
    "throughout, at medical/technical-illustration precision — never hazy, soft-focus, "
    "dreamlike, or atmospheric-abstract. Sophisticated rather than playful; technically "
    "credible.",
    "Never: cartoon characters, generic stock-photo appearance, excessive glow or large glowing "
    "halos, cyberpunk styling, or an obvious AI-generated-poster look.",
)

# The editorial family — the ONE place membership lives. Both the constraint routing below and the
# light-palette routing in the sibling ``light`` module derive from this set, so a future editorial
# preset can't end up with an editorial dark render but the GENERAL azure light twin.
EDITORIAL_PRESETS: frozenset[CoverStylePreset] = frozenset(
    {CoverStylePreset.NOCTURNE, CoverStylePreset.BLUEPRINT, CoverStylePreset.AURORA}
)

# Per-preset medium/mood. The preset varies the look; it never relaxes a shared constraint above.
_PRESET_DIRECTIVES: dict[CoverStylePreset, str] = {
    CoverStylePreset.GENERAL: (
        "Preset GENERAL (the house default): a premium enterprise-learning course cover — one "
        "dominant hero visualization of the subject with a few supporting elements, rendered as a "
        "modern editorial infographic fused with refined 3D illustration on a dark graphite "
        "ground with selective amber lighting."
    ),
    CoverStylePreset.NOCTURNE: (
        "Preset NOCTURNE: a night-sky editorial illustration — a single "
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

# Which constraint set each preset obeys — GENERAL has its own; the editorial family shares the
# original locked set. Derived from EDITORIAL_PRESETS so membership lives in one place.
_PRESET_CONSTRAINTS: dict[CoverStylePreset, tuple[str, ...]] = {
    preset: (_EDITORIAL_CONSTRAINTS if preset in EDITORIAL_PRESETS else _GENERAL_CONSTRAINTS)
    for preset in CoverStylePreset
}


@dataclass(frozen=True)
class HouseStyle:
    """The house-style brief for one preset: its constraints plus that preset's medium/mood.

    ``constraints`` carry the anti-slop discipline (the shared core + the preset family's own
    rules); ``preset_directive`` is the preset-specific medium. Both the art director's prompt and
    the QA rubric read from here so they share one definition of the style.
    """

    constraints: tuple[str, ...]
    preset_directive: str

    def as_prompt_block(self) -> str:
        """The constraints + preset directive rendered as a numbered block for a prompt/rubric."""
        rules = "\n".join(f"{n}. {rule}" for n, rule in enumerate(self.constraints, start=1))
        return f"{self.preset_directive}\n\nNON-NEGOTIABLE CONSTRAINTS:\n{rules}"


def house_style(preset: CoverStylePreset) -> HouseStyle:
    """The constraints plus the medium/mood for ``preset`` (the DARK base render's style).

    An unknown preset falls back to the house ``GENERAL`` directive rather than raising — a cover
    is always designable — while still carrying the full anti-slop discipline. The LIGHT-theme
    twin's look lives in the sibling ``light`` module.
    """
    directive = _PRESET_DIRECTIVES.get(preset, _PRESET_DIRECTIVES[CoverStylePreset.GENERAL])
    constraints = _PRESET_CONSTRAINTS.get(preset, _PRESET_CONSTRAINTS[CoverStylePreset.GENERAL])
    return HouseStyle(constraints=constraints, preset_directive=directive)
