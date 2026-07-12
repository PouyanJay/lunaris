"""The GENERAL preset (cover-general-preset): the premium enterprise-infographic house default.

Distilled from the operator's course-cover prompt system: a modern editorial infographic fused with
refined 3D illustration — one dominant hero visualization plus a few supporting elements, generous
negative space, premium materials — with the SAME no-text anti-slop discipline as the editorial
presets. Its dark ground is graphite + amber; its LIGHT twin re-themes to white + azure (unlike the
editorial presets, whose light twin stays ivory + amber). GENERAL is the default: the fallback for
an unknown preset and the product default when nothing is configured.
"""

import pytest
from lunaris_covers.art_direction.house_style import (
    GENERAL_DARK_THEME,
    GENERAL_LIGHT_THEME,
    build_general_prompt,
    house_style,
    light_retheme_instruction,
    light_style_block,
    native_light_prompt,
)
from lunaris_covers.schemas.general_cover_fields import GeneralCoverFields
from lunaris_runtime.cover_build import DEFAULT_COVER_CONFIG
from lunaris_runtime.schema import CoverJob, CoverStylePreset


def test_general_preset_exists_and_is_the_schema_default() -> None:
    assert CoverStylePreset.GENERAL.value == "general"
    job = CoverJob(id="j", user_id="u", course_id="c", input_hash="h")
    assert job.style_preset is CoverStylePreset.GENERAL


def test_general_is_the_product_default_cover_config() -> None:
    assert DEFAULT_COVER_CONFIG.style_preset is CoverStylePreset.GENERAL


def test_general_block_is_the_premium_enterprise_style() -> None:
    block = house_style(CoverStylePreset.GENERAL).as_prompt_block()
    lowered = block.lower()
    # The user's prompt system, distilled: hero + supporting elements, editorial-infographic + 3D.
    assert "hero" in lowered
    assert "supporting" in lowered
    assert "infographic" in lowered
    assert "3d" in lowered
    # Dark ground stays brand-anchored: graphite/near-black + amber accents.
    assert "amber" in lowered
    assert "near-black" in lowered or "graphite" in lowered
    # And its avoid-list guards the premium finish.
    assert "cyberpunk" in lowered and "cartoon" in lowered


def test_general_block_requires_correct_typography_not_a_wordless_cover() -> None:
    # general-cover-typography: the GENERAL cover typesets its own title — the wordless "NO text"
    # rule is exactly what kept covers looking like bare illustrations. It must instead demand
    # correctly-spelled lettering, and the gate rejects garbles.
    lowered = house_style(CoverStylePreset.GENERAL).as_prompt_block().lower()
    assert "typography" in lowered
    assert "correctly spelled" in lowered
    assert "no text" not in lowered  # the wordless rule must NOT apply to GENERAL


def test_editorial_blocks_stay_wordless() -> None:
    for preset in (CoverStylePreset.NOCTURNE, CoverStylePreset.BLUEPRINT, CoverStylePreset.AURORA):
        assert "no text" in house_style(preset).as_prompt_block().lower()


def test_general_block_does_not_mandate_the_flat_illustration_finish() -> None:
    # The editorial presets demand a matte FLAT-illustration finish and forbid 3D; GENERAL is a
    # refined-3D style, so inheriting that constraint would make every general cover fail QA.
    block = house_style(CoverStylePreset.GENERAL).as_prompt_block().lower()
    assert "flat-illustration" not in block


@pytest.mark.parametrize(
    "preset",
    [CoverStylePreset.NOCTURNE, CoverStylePreset.BLUEPRINT, CoverStylePreset.AURORA],
)
def test_editorial_preset_keeps_its_locked_constraints(preset: CoverStylePreset) -> None:
    block = house_style(preset).as_prompt_block().lower()
    assert "flat-illustration" in block  # the editorial discipline is untouched
    assert "no text" in block


def test_unknown_preset_falls_back_to_general() -> None:
    block = house_style("does-not-exist").as_prompt_block().lower()  # type: ignore[arg-type]
    assert "hero" in block  # the GENERAL directive, not nocturne


def test_general_light_twin_is_white_plus_azure() -> None:
    instruction = light_retheme_instruction(CoverStylePreset.GENERAL).lower()
    assert "azure" in instruction
    assert "white" in instruction or "pale" in instruction
    assert "amber" not in instruction  # azure replaces the amber accent in light mode
    rubric = light_style_block(CoverStylePreset.GENERAL).lower()
    assert "azure" in rubric
    assert "no text" in rubric


def test_editorial_light_twin_keeps_ivory_plus_amber() -> None:
    instruction = light_retheme_instruction(CoverStylePreset.NOCTURNE).lower()
    assert "amber" in instruction
    assert "azure" not in instruction
    rubric = light_style_block(CoverStylePreset.NOCTURNE).lower()
    assert "amber" in rubric and "azure" not in rubric


# ---- general-preset template fidelity: the image model sees the FULL operator template ----


def _fields() -> GeneralCoverFields:
    return GeneralCoverFields(
        subject="The HTTP request/response lifecycle between a browser and a server",
        primary_visual="a refined 3D laptop communicating with a modern server stack",
        supporting_visuals="request/response paths, protocol layers, message cards",
        process_visualization="a bidirectional client-server flow",
        eyebrow="PROFESSIONAL EDUCATION COURSE",
        title_lines=["How", "HTTP", "Works"],
        highlight_line="HTTP",
        subtitle="Understand the protocol that powers the web",
        badges=["FOUNDATIONAL", "PRACTICAL", "ESSENTIAL"],
        callouts=["TLS", "TCP"],
    )


def test_general_prompt_is_the_operator_template_verbatim() -> None:
    # The regression this pins: the pipeline used to compress the spec into 2-4 sentences of prose,
    # so the image model never saw the template — and outputs looked nothing like the references.
    prompt = build_general_prompt(
        title="How HTTP Works", key_concepts="requests, responses, headers", fields=_fields()
    )
    # Framing context + every section header, verbatim.
    assert "Create a premium, enterprise-grade 16:9 educational course cover" in prompt
    assert "Key concepts to convey: requests, responses, headers" in prompt
    # Landmark lines the compression used to drop.
    assert "Keep ALL of this typography in the left third" in prompt
    assert "Premium pharmaceutical / enterprise-education design" in prompt
    assert "AI-generated-poster look" in prompt
    # The dark amber theme block rides verbatim, and the fields landed in their slots.
    assert GENERAL_DARK_THEME in prompt
    assert "a refined 3D laptop communicating" in prompt
    assert "- Hero: a refined 3D laptop" in prompt


def test_native_light_prompt_swaps_only_the_theme_block_for_general() -> None:
    dark = build_general_prompt(title="T", key_concepts="k", fields=_fields())
    light = native_light_prompt(dark, CoverStylePreset.GENERAL)
    assert GENERAL_LIGHT_THEME in light and GENERAL_DARK_THEME not in light
    # Everything else — subject fields, composition, style — is byte-identical.
    assert light.replace(GENERAL_LIGHT_THEME, GENERAL_DARK_THEME) == dark


def test_native_light_prompt_appends_the_directive_for_editorial() -> None:
    prose = "A lone amber lighthouse over a near-black sea."
    light = native_light_prompt(prose, CoverStylePreset.NOCTURNE)
    assert light.startswith(prose)
    assert "LIGHT MODE" in light and "amber" in light.lower()


def test_general_retheme_instruction_carries_the_azure_theme_verbatim() -> None:
    instruction = light_retheme_instruction(CoverStylePreset.GENERAL)
    assert GENERAL_LIGHT_THEME in instruction
    assert "Preserve the exact composition" in instruction


def test_native_light_prompt_falls_back_to_append_without_the_dark_block() -> None:
    # The defensive branch: a general prompt missing the verbatim dark theme block (should not
    # happen) still gets a light attempt via the append shape rather than being skipped.
    light = native_light_prompt("a prompt with no theme block", CoverStylePreset.GENERAL)
    assert light.startswith("a prompt with no theme block")
    assert "LIGHT MODE" in light and GENERAL_LIGHT_THEME in light


# ---- general-literal-diagram-style: literal textbook depiction, separated components, no haze ----


def test_general_block_demands_literal_textbook_depiction() -> None:
    # The operator's references are textbook-accurate diagrams of the ACTUAL mechanism. The
    # inherited "evocative, not literal" rule steered renders into abstract blobs — for GENERAL it
    # is inverted: literal depiction, separated diagram components, crisp detail, no haze.
    block = house_style(CoverStylePreset.GENERAL).as_prompt_block()
    lowered = block.lower()
    assert "literal" in lowered and "textbook" in lowered
    assert "evocative" not in lowered  # the editorial philosophy must not leak in
    assert "separate" in lowered and "magnified" in lowered  # diagram grammar: discrete components
    assert "never hazy" in lowered  # the anti-cloud rule


def test_editorial_blocks_keep_the_evocative_philosophy() -> None:
    block = house_style(CoverStylePreset.NOCTURNE).as_prompt_block().lower()
    assert "evocative" in block and "not a literal" in block


def test_general_prompt_carries_the_educational_accuracy_guardrails() -> None:
    # From the operator's ChatGPT tooling: an EDUCATIONAL ACCURACY section with domain guardrails,
    # so the cover cannot be confidently wrong (a cover that misteaches is worse than a plain one).
    fields = _fields().model_copy(
        update={"accuracy_requirements": ["keep eosinophils distinct from generic blood cells"]}
    )
    prompt = build_general_prompt(title="T", key_concepts="k", fields=fields)
    assert "EDUCATIONAL ACCURACY:" in prompt
    assert "never depict a misleading scientific" in prompt
    assert "- keep eosinophils distinct from generic blood cells" in prompt
    # And the QA rubric judges the same rule, so the gate can reject a misteaching cover.
    assert "misteaches" in house_style(CoverStylePreset.GENERAL).as_prompt_block()


def test_general_is_a_cover_not_a_lecture_slide() -> None:
    # The operator's density note: the first composed render read as a dense infographic — every
    # concept demanding its own labelled callout. A cover reads at a glance and invites the learner
    # in; it does not teach the syllabus. Pinned in BOTH the prompt and the QA rubric.
    prompt = build_general_prompt(title="T", key_concepts="k", fields=_fields())
    assert "COURSE COVER, not a lecture slide" in prompt
    assert "COMPOSE FOR CALM" in prompt
    assert "MARGINS ARE HARD" in prompt

    rubric = house_style(CoverStylePreset.GENERAL).as_prompt_block()
    assert "not a lecture slide" in rubric  # the gate rejects a crowded cover
    assert "MARGINS" in rubric  # ... and one whose subject bleeds off an edge
    assert "whole pair of lungs, not one airway" in rubric  # the whole-subject hero anchor


def test_callouts_are_capped_at_two() -> None:
    # The density dial: four labelled callouts turned the cover into a lecture slide.
    assert GeneralCoverFields.model_fields["callouts"].metadata[0].max_length == 2
