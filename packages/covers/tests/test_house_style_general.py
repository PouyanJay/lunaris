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
    house_style,
    light_retheme_instruction,
    light_style_block,
)
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
    # The no-text discipline (the #1 slop tell) is NON-NEGOTIABLE for every preset.
    assert "no text" in lowered
    # And its avoid-list guards the premium finish.
    assert "cyberpunk" in lowered and "cartoon" in lowered


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
