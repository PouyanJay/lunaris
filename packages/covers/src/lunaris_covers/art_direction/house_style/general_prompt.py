"""The GENERAL preset's full image prompt — the operator's template, assembled deterministically.

The operator's course-cover prompt system produces its reference look by sending a complete,
structured prompt to the image model VERBATIM: LAYOUT (the typography), the MAIN VISUAL, VISUAL
STYLE, COLOR PALETTE and OUTPUT. The pipeline once had Claude compress all of that into 2-4
sentences of prose, which is why generated covers looked nothing like the references. Here the LLM
fills only the fields (``GeneralCoverFields``); everything else is this template, byte-stable.

Two lessons are baked in, both learned by A/B-ing a render against the operator's reference
(general-cover-typography):

* **The cover carries its own typography.** The reference is a *composed cover* — eyebrow, stacked
  title with one line in amber, subtitle, three captioned badges, small scientific callouts — all
  typeset by the image model. The pipeline's original "NO text anywhere" rule (written when image
  models garbled letterforms) is exactly what kept covers looking like bare illustrations. GPT
  Image 2 typesets reliably; the vision-QA gate verifies the title's spelling and re-rolls a garble.
* **Amber is the GRADE, not an accent.** Told to use "amber accents", the model rendered a subject
  in natural colors (pink tissue, red vessels) and lit it amber — a pathology plate. The reference
  rim-lights the entire subject in amber and keeps other hues *restrained*, which is what makes it
  read as a branded cover.

The theme blocks live in their own sibling modules (one export per file); this module owns the
template and its builder.
"""

from lunaris_covers.schemas.general_cover_fields import GeneralCoverFields

from .general_dark_theme import GENERAL_DARK_THEME

_TEMPLATE = """\
Create a premium, enterprise-grade 16:9 educational course cover for a professional learning \
platform.

LAYOUT (render this text INTO the image, typeset cleanly and spelled EXACTLY as given):
- A small outlined pill label at the upper left reading: {eyebrow}
- Below it, the course title in a large, bold, modern sans-serif, broken across these lines \
exactly as written, stacked left-aligned:
{title_block}
- Typeset the line "{highlight_line}" in rich amber; the other title lines in clean white.
- A short amber rule beneath the title, then the subtitle in white on one or two lines: {subtitle}
- Along the lower left, three small circular outlined icons in a row, each with a short ALL-CAPS \
caption beneath it: {badges}
- Keep ALL of this typography in the left third of the frame, generously spaced, never overlapping \
the artwork.
- Every letterform must be crisp, correctly spelled and legible. No lorem ipsum, no invented \
words, no duplicated text.

MAIN VISUAL (the right two-thirds):
- Subject: {subject}
- Key concepts to convey: {key_concepts}
- Hero: {primary_visual}
- Supporting elements: {supporting_visuals}
- Relationship to show: {process_visualization}
- Lead with the whole, immediately recognizable subject as the anchor, then add a dramatic \
magnified circular cutaway/inset revealing its internal detail, plus discrete floating components \
around it. Every element fully inside the frame with comfortable margins — nothing cropped by the \
edges.
{callout_block}

VISUAL STYLE:
- Premium pharmaceutical / enterprise-education design
- Refined 3D scientific illustration, scientifically credible but visually dramatic
- Literal, anatomically and technically accurate depiction of the real subject — never an abstract \
metaphor or mood piece
- Detailed, crisp structures at medical-illustration precision; sharp edges, high-frequency detail
- Sophisticated editorial infographic layout with strong visual hierarchy and clean spacing
- High-end studio lighting, subtle depth of field, elegant and gallery-grade — never clinical, \
gory, hazy, soft-focus or dreamlike
- No cartoon appearance, no generic stock-photo look, no cyberpunk styling, no obvious \
AI-generated-poster look

COLOR PALETTE:
{theme}
- Amber is the DOMINANT GRADE, not a highlight: rim-light the entire subject — organs, \
structures, cells, components — in amber and gold so the whole frame reads as one warm, \
branded family.
- Keep any naturalistic colors (reds, pinks, greens, blues) RESTRAINED and subordinate to the \
amber \
grade; never let the subject render in ordinary naturalistic colors.
- Background predominantly near-black and charcoal; amber accents controlled and premium.

OUTPUT:
- 16:9 landscape course cover, high quality
- Typography in the left third, artwork in the center-right
- Clear, legible, correctly spelled text
- Balanced, professional, premium composition"""

_CALLOUT_LINE = (
    "- Add small scientific callout labels with thin leader lines beside the relevant parts of the "
    "artwork, spelled exactly: {callouts}"
)


def build_general_prompt(
    *,
    title: str,
    key_concepts: str,
    fields: GeneralCoverFields,
    theme: str = GENERAL_DARK_THEME,
) -> str:
    """The complete GENERAL cover prompt: the operator's template with the fields filled.

    ``title`` is the course title (the source of truth the QA gate checks the rendered typography
    against); ``key_concepts`` grounds the subject matter; ``fields`` are the LLM-generated artwork
    descriptions and typographic content; ``theme`` selects the COLOR PALETTE block (dark amber by
    default — the base render; the light path passes the azure block). Assembled with plain
    substitution, no model in the loop, so the image model always sees the full spec.
    """
    # ``title`` is not interpolated — fields.title_lines carries the typeset form; it stays in the
    # signature because it is the QA gate's source of truth for the spelling check.
    _ = title
    title_block = "\n".join(f'    "{line}"' for line in fields.title_lines)
    badges = " / ".join(fields.badges)
    callout_block = (
        _CALLOUT_LINE.format(callouts=", ".join(fields.callouts)) if fields.callouts else ""
    )
    return _TEMPLATE.format(
        eyebrow=fields.eyebrow,
        title_block=title_block,
        highlight_line=fields.highlight_line,
        subtitle=fields.subtitle,
        badges=badges,
        subject=fields.subject,
        primary_visual=fields.primary_visual,
        supporting_visuals=fields.supporting_visuals,
        process_visualization=fields.process_visualization,
        callout_block=callout_block,
        key_concepts=key_concepts,
        theme=theme,
    )
