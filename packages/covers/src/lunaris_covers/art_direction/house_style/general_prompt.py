"""The GENERAL preset's full image prompt — the operator's template, assembled deterministically.

The operator's course-cover prompt system produces its reference look by sending a complete,
structured prompt to the image model VERBATIM: framing context, COMPOSITION, SUBJECT VISUALIZATION,
STYLE, COLOR THEME, LIGHTING AND MATERIALS, and OUTPUT sections. The original pipeline instead had
Claude compress everything into 2-4 sentences of prose — which is exactly why generated covers
looked nothing like the references (general-preset template fidelity). Here the LLM fills only the
descriptive fields (``GeneralCoverFields``); everything else is this template, byte-stable.

The three public constants/functions are tightly-coupled siblings of one contract: the template
builder, and the two COLOR THEME blocks (dark amber / light azure) that the light-variant module
reuses so the re-theme instruction and the native-light rebuild carry the operator's exact theme
text. One deliberate deviation from the source doc: the OUTPUT section says "wide landscape" rather
than "16:9" — the Images API renders 1536x1024 (3:2), which matches the operator's reference images.
"""

from lunaris_covers.schemas.general_cover_fields import GeneralCoverFields

# § Dark Mode Theme: Amber — verbatim from the operator's prompt system.
GENERAL_DARK_THEME = """\
Use a near-black, charcoal, and deep graphite background with amber as the dominant accent color.

Use rich amber, golden orange, warm honey highlights, dark bronze, muted copper, warm ivory, and \
soft neutral gray.

Apply amber lighting selectively to important components. Keep the background predominantly dark \
and sophisticated.

Avoid:
- Neon yellow
- Excessive orange saturation
- Large glowing halos
- Blue accents
- Purple accents
- Flat pure black without dimensional variation
- Cyberpunk styling"""

# § Light Mode Theme: Azure — verbatim from the operator's prompt system.
GENERAL_LIGHT_THEME = """\
Use a clean white, soft ivory, or very pale cool-gray background with Azure blue as the dominant \
accent color.

Use Azure blue, clear medium blue, navy, slate blue, pale sky blue, cool silver, and soft neutral \
gray.

Apply Azure to important components, directional paths, active states, and focal highlights. Keep \
most surfaces white or very light with subtle blue-gray shadows.

Avoid:
- Large areas of dark navy
- Excessive cyan
- Neon glow
- Purple accents
- Flat sterile white backgrounds without depth
- Cartoon or playful styling"""

# § Reusable Course Cover Prompt — verbatim, with the template variables as format fields.
_TEMPLATE = """\
Create a premium, enterprise-grade educational course cover for the following course.

Course title: "{title}"
Course subtitle: "{subtitle}"
Course subject: "{subject}"
Key concepts: "{key_concepts}"

Create a polished wide-landscape course-cover image.

COMPOSITION:
- Reserve approximately 38% of the left side as clean negative space for text that will be added \
later by the application.
- Place the main subject visualization across the center and right side.
- Use one dominant hero illustration with two to four supporting visual elements.
- Keep the composition readable at thumbnail size.
- Keep important elements away from the edges.
- Do not place any readable text, titles, labels, numbers, logos, or watermarks inside the \
generated image.

SUBJECT VISUALIZATION:
- Primary visual: {primary_visual}
- Supporting visuals: {supporting_visuals}
- Process or relationship to illustrate: {process_visualization}

Translate the course topic into an intuitive visual using dimensional diagrams, connected \
components, flowing paths, layered systems, scientific structures, or step-by-step relationships \
where appropriate.

STYLE:
- Premium enterprise learning platform
- Modern editorial infographic combined with refined 3D illustration
- Clean geometry and precise spacing
- Realistic, polished materials
- Subtle dimensional depth
- Sophisticated rather than playful
- Scientifically or technically credible
- Minimal visual clutter
- No cartoon characters
- No generic stock-photo appearance
- No excessive glow
- No cyberpunk styling
- No obvious AI-generated poster appearance

COLOR THEME:
{theme}

LIGHTING AND MATERIALS:
- Soft, controlled studio lighting
- Subtle shadows and ambient occlusion
- Refined glass, matte metal, ceramic, translucent, or technical materials where appropriate
- Strong separation between foreground and background
- Restrained highlights matching the theme accent color

OUTPUT:
- Wide landscape
- High-resolution
- Clean left-side text area
- Main artwork concentrated toward the center-right
- Suitable for a modern professional course-building application"""


def build_general_prompt(
    *,
    title: str,
    key_concepts: str,
    fields: GeneralCoverFields,
    theme: str = GENERAL_DARK_THEME,
) -> str:
    """The complete GENERAL cover prompt: the operator's template with the variables filled.

    ``title``/``key_concepts`` come from the course (the brief); ``fields`` are the LLM-generated
    descriptions; ``theme`` selects the COLOR THEME block (dark amber by default — the base render;
    the light-variant path passes ``GENERAL_LIGHT_THEME``). Assembled with plain substitution, no
    model in the loop, so the image model always sees the full spec.
    """
    return _TEMPLATE.format(
        title=title,
        subtitle=fields.subtitle,
        subject=fields.subject,
        key_concepts=key_concepts,
        primary_visual=fields.primary_visual,
        supporting_visuals=fields.supporting_visuals,
        process_visualization=fields.process_visualization,
        theme=theme,
    )
