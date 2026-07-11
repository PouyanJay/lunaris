"""CoverVisionQa contract (course-cover-images T5): the anti-slop vision gate.

The inspector prompts a vision model with the house-style rubric + the rendered image and parses a
structured verdict (pass, or a list of named defects) with bounded parse-repair. It is exercised
against a fake ``VisionInvoke`` (never a live call): the rubric carries the locked constraints, a
clean image passes, a slop image fails with defects, and a malformed completion is repaired.
"""

import pytest
from lunaris_covers.models.cover_brief import CoverBrief
from lunaris_covers.qa.cover_vision_qa import CoverVisionQa
from lunaris_runtime.schema import CoverStylePreset

_BRIEF = CoverBrief(
    topic="How HTTPS works",
    concept_labels=("TCP handshake", "TLS"),
    audience="engineers",
    style_preset=CoverStylePreset.NOCTURNE,
)
_IMAGE = b"\x89PNG_fake_bytes"


class _StubVisionInvoke:
    """A fake ``VisionInvoke``: records the (prompt, images) it saw, returns canned replies."""

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.prompt: str | None = None
        self.images: list[bytes] | None = None
        self.calls = 0

    async def __call__(self, prompt: str, images: list[bytes]) -> str:
        self.calls += 1
        self.prompt = prompt
        self.images = images
        return self._replies.pop(0)


@pytest.mark.asyncio
async def test_clean_image_passes_with_no_defects() -> None:
    invoke = _StubVisionInvoke('{"passed": true}')

    verdict = await CoverVisionQa(invoke=invoke, model="claude-opus-4-8").inspect(_IMAGE, _BRIEF)

    assert verdict.passed is True
    assert verdict.defects == []
    assert invoke.images == [_IMAGE]  # the rendered cover is handed to the vision model


@pytest.mark.asyncio
async def test_slop_image_fails_with_named_defects() -> None:
    reply = '{"passed": false, "defects": [{"issue": "garbled text along the bottom edge"}]}'
    invoke = _StubVisionInvoke(reply)

    verdict = await CoverVisionQa(invoke=invoke, model="claude-opus-4-8").inspect(_IMAGE, _BRIEF)

    assert verdict.passed is False
    assert verdict.defects[0].issue == "garbled text along the bottom edge"


@pytest.mark.asyncio
async def test_rubric_carries_the_locked_house_style_constraints() -> None:
    invoke = _StubVisionInvoke('{"passed": true}')

    await CoverVisionQa(invoke=invoke, model="claude-opus-4-8").inspect(_IMAGE, _BRIEF)

    assert invoke.prompt is not None
    # The #1 slop tell (text in the image) must be in the rubric the judge audits against.
    assert "NO text" in invoke.prompt or "no text" in invoke.prompt.lower()


@pytest.mark.asyncio
async def test_dark_rubric_demands_a_near_black_ground() -> None:
    invoke = _StubVisionInvoke('{"passed": true}')

    await CoverVisionQa(invoke=invoke, model="claude-opus-4-8").inspect(_IMAGE, _BRIEF)

    assert invoke.prompt is not None
    assert "near-black" in invoke.prompt.lower()  # the dark rubric's ground constraint


@pytest.mark.parametrize(
    ("preset", "expected_accent", "forbidden_accent"),
    [
        (CoverStylePreset.NOCTURNE, "amber", "azure"),  # editorial light = ivory + amber
        (CoverStylePreset.GENERAL, "azure", "amber"),  # general light = white + azure
    ],
)
@pytest.mark.asyncio
async def test_light_variant_is_judged_against_its_presets_bright_rubric(
    preset: CoverStylePreset, expected_accent: str, forbidden_accent: str
) -> None:
    # A light-theme variant must be judged against the LIGHT rubric — the dark rubric's dark ground
    # would reject any correct light cover — and against the BRIEF's preset palette: a hardcoded
    # preset in CoverVisionQa.inspect would judge a general cover on amber and fail this test.
    brief = CoverBrief(
        topic="How HTTPS works",
        concept_labels=("TCP handshake", "TLS"),
        audience="engineers",
        style_preset=preset,
    )
    invoke = _StubVisionInvoke('{"passed": true}')

    await CoverVisionQa(invoke=invoke, model="claude-opus-4-8").inspect(_IMAGE, brief, light=True)

    assert invoke.prompt is not None
    lowered = invoke.prompt.lower()
    assert "light" in lowered
    assert expected_accent in lowered and forbidden_accent not in lowered
    assert "near-black night-sky ground" not in lowered  # not the dark ground constraint
    assert "no text" in lowered  # the shared anti-slop discipline still holds


@pytest.mark.asyncio
async def test_malformed_completion_is_repaired() -> None:
    invoke = _StubVisionInvoke("not json at all", '{"passed": true}')

    verdict = await CoverVisionQa(invoke=invoke, model="claude-opus-4-8").inspect(_IMAGE, _BRIEF)

    assert verdict.passed is True
    assert invoke.calls == 2  # first reply rejected → one repair turn


@pytest.mark.asyncio
async def test_inconsistent_verdict_is_rejected_then_repaired() -> None:
    # "passed with defects" is contradictory → a parse failure, not a silently shipped slop cover.
    bad = '{"passed": true, "defects": [{"issue": "busy"}]}'
    invoke = _StubVisionInvoke(bad, '{"passed": false, "defects": [{"issue": "busy, cluttered"}]}')

    verdict = await CoverVisionQa(invoke=invoke, model="claude-opus-4-8").inspect(_IMAGE, _BRIEF)

    assert verdict.passed is False
    assert invoke.calls == 2
