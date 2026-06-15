"""SceneCodeGenerator tests (stubbed model): the deterministic source gate — no-LaTeX rule,
required class, style import, syntax — and the bounded format-repair loop around it."""

from collections.abc import Callable

import pytest
from _stubs import StubInvokeModel
from lunaris_video.codegen import SceneCodeGenerator, validate_scene_source
from lunaris_video.schemas import BeatTiming, QaDefect, SceneContract, SceneTiming


def _timing_for(scene: SceneContract) -> SceneTiming:
    # A distinct, non-round window per beat so a test can spot the exact value in the prompt.
    beats = [
        BeatTiming(id=beat.id, audio_s=0.0, anim_s=round(2.5 + i, 2), audio=None, estimated=True)
        for i, beat in enumerate(scene.beats)
    ]
    return SceneTiming(beats=beats, total_s=round(sum(b.anim_s for b in beats), 2))


_VALID_SOURCE = """\
from manim import *
from style_tokens import *


class S1Problem(Scene):
    def construct(self):
        title = title_bar("Sorting")
        self.play(FadeIn(title))
        clear_scene(self)
"""


def _valid_source_for(scene: SceneContract) -> str:
    # The validator rejects a class name that does not match the scene, so a repair test whose scene
    # is not S1Problem needs source carrying that scene's own class name.
    return _VALID_SOURCE.replace("S1Problem", scene.scene_class_name)


async def test_generate_returns_validated_source(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — the model wraps its code in fences; the validator strips them.
    stub = StubInvokeModel([f"```python\n{_VALID_SOURCE}```"])
    codegen = SceneCodeGenerator(invoke=stub)
    scene = make_scene(1, "problem")

    # Act
    source = await codegen.generate(scene, topic="merge sort", timing=_timing_for(scene))

    # Assert
    assert source.startswith("from manim import *")
    assert "class S1Problem(Scene):" in source
    assert "```" not in source


async def test_generate_prompt_carries_contract_and_patterns(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange
    stub = StubInvokeModel([_VALID_SOURCE])
    codegen = SceneCodeGenerator(invoke=stub)
    scene = make_scene(1, "problem")

    # Act
    await codegen.generate(scene, topic="merge sort", timing=_timing_for(scene))

    # Assert — the scene's contract JSON, the pinned no-pivot rule, and the exact class name
    # the renderer will select are all in the prompt.
    prompt = stub.prompts[0]
    assert scene.id in prompt
    assert "never rotate about get_center()" in prompt
    assert "class S1Problem(Scene):" in prompt


async def test_generate_prompt_carries_the_exact_beat_timing_windows(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — audio-drives-video: the codegen must receive each beat's FIXED on-screen window so
    # the generated scene's run_times/waits sum to it (not just honour min_visual_s).
    stub = StubInvokeModel([_VALID_SOURCE])
    codegen = SceneCodeGenerator(invoke=stub)
    scene = make_scene(1, "problem")
    timing = _timing_for(scene)

    # Act
    await codegen.generate(scene, topic="merge sort", timing=timing)

    # Assert — every beat id and its exact window second are in the prompt.
    prompt = stub.prompts[0]
    for beat in timing.beats:
        assert beat.id in prompt
        assert f"{beat.anim_s}" in prompt


async def test_generate_prompt_tells_the_model_to_front_load_each_reveal(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — sync is deterministic only if the narrated element is on screen by the beat MIDPOINT
    # (where Gate D samples). The generate prompt must instruct the model to front-load each reveal,
    # so it doesn't build the named element up across the window and desync at the midpoint.
    stub = StubInvokeModel([_VALID_SOURCE])
    codegen = SceneCodeGenerator(invoke=stub)
    scene = make_scene(1, "problem")

    # Act
    await codegen.generate(scene, topic="merge sort", timing=_timing_for(scene))

    # Assert — the prompt names the midpoint constraint and the front-load fix.
    prompt = stub.prompts[0].lower()
    assert "midpoint" in prompt
    assert "front-load" in prompt


async def test_latex_in_a_completion_triggers_a_repair_turn(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — first completion smuggles MathTex (the no-LaTeX rule's whole reason to exist).
    bad = _VALID_SOURCE.replace('title_bar("Sorting")', 'MathTex(r"\\frac{1}{2}")')
    stub = StubInvokeModel([bad, _VALID_SOURCE])
    codegen = SceneCodeGenerator(invoke=stub)
    scene = make_scene(1, "problem")

    # Act
    source = await codegen.generate(scene, topic="merge sort", timing=_timing_for(scene))

    # Assert
    assert len(stub.prompts) == 2
    assert "MathTex" in stub.prompts[1]  # the repair turn names the violation
    assert "MathTex" not in source


async def test_repair_prompt_embeds_source_and_stack_trace(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange
    stub = StubInvokeModel([_VALID_SOURCE])
    codegen = SceneCodeGenerator(invoke=stub)
    failing_source = _VALID_SOURCE.replace("FadeIn", "FadeInFrom")
    scene = make_scene(1, "problem")

    # Act
    await codegen.repair(
        scene,
        source=failing_source,
        error_tail="NameError: name 'FadeInFrom' is not defined",
        timing=_timing_for(scene),
    )

    # Assert — the model sees exactly what failed and how.
    prompt = stub.prompts[0]
    assert "FadeInFrom" in prompt
    assert "NameError" in prompt


async def test_both_repair_prompts_keep_the_beat_timing_windows(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — a repaired scene must still hit its windows, so both repair templates carry timing.
    scene = make_scene(1, "problem")
    timing = _timing_for(scene)

    # Act — drive each repair arm once.
    render_stub = StubInvokeModel([_VALID_SOURCE])
    await SceneCodeGenerator(invoke=render_stub).repair(
        scene, source=_VALID_SOURCE, error_tail="boom", timing=timing
    )
    visual_stub = StubInvokeModel([_VALID_SOURCE])
    await SceneCodeGenerator(invoke=visual_stub).repair_visual(
        scene,
        source=_VALID_SOURCE,
        defects=[QaDefect(issue="overlap", fix_hint="separate them")],
        timing=timing,
    )

    # Assert — both repair prompts carry every beat's exact window (not just the generate prompt).
    for stub in (render_stub, visual_stub):
        prompt = stub.prompts[0]
        for beat in timing.beats:
            assert beat.id in prompt
            assert f"{beat.anim_s}" in prompt


async def test_repair_sync_prompt_carries_the_beat_reason_and_front_load_fix(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — Gate D's repair turn must tell the model EXACTLY what desynced (which beat + the
    # vision reason) and the fix (move the reveal to the start so it's on screen by the midpoint).
    # Without a live run this is the only check that the core repair prompt isn't watered down.
    stub = StubInvokeModel([_VALID_SOURCE])
    codegen = SceneCodeGenerator(invoke=stub)
    scene = make_scene(1, "problem")
    timing = _timing_for(scene)

    # Act
    await codegen.repair_sync(
        scene,
        source=_VALID_SOURCE,
        beat_id="b2",
        reason="the loss is named but not on screen yet",
        timing=timing,
    )

    # Assert — the offending beat, the verbatim vision reason, the front-load instruction, and the
    # midpoint constraint are all in the prompt, plus the unchanged beat-timing windows.
    prompt = stub.prompts[0]
    assert "b2" in prompt
    assert "the loss is named but not on screen yet" in prompt
    lowered = prompt.lower()
    assert "start" in lowered  # "move the reveal ... to the START of this beat's window"
    assert "midpoint" in lowered
    for beat in timing.beats:
        assert f"{beat.anim_s}" in prompt  # the windows still ride along (timing unchanged)


async def test_visual_repair_prompt_adds_hook_title_guidance_for_a_hook_scene(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — a hook scene is the stubborn Gate-B archetype; its visual-repair prompt gets the
    # extra targeted guidance (overflow / contrast / overlap) so the repair has a better shot.
    scene = make_scene(1, "hook")
    stub = StubInvokeModel([_valid_source_for(scene)])
    codegen = SceneCodeGenerator(invoke=stub)

    # Act
    await codegen.repair_visual(
        scene,
        source=_valid_source_for(scene),
        defects=[QaDefect(issue="title overflows", fix_hint="scale it")],
        timing=_timing_for(scene),
    )

    # Assert — the hook/title hint is present, naming the concrete fix.
    prompt = stub.prompts[0]
    assert "HOOK / TITLE" in prompt
    assert "scale_to_fit_width" in prompt


async def test_visual_repair_prompt_omits_hook_guidance_for_a_body_scene(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — an ordinary mechanism scene is not a hook/title, so the prompt stays focused on its
    # own defects without the title-card guidance.
    scene = make_scene(2, "mechanism")
    stub = StubInvokeModel([_valid_source_for(scene)])
    codegen = SceneCodeGenerator(invoke=stub)

    # Act
    await codegen.repair_visual(
        scene,
        source=_valid_source_for(scene),
        defects=[QaDefect(issue="overlap", fix_hint="separate")],
        timing=_timing_for(scene),
    )

    # Assert
    assert "HOOK / TITLE" not in stub.prompts[0]


@pytest.mark.parametrize(
    "violation",
    [
        'Tex(r"x")',
        'MathTex(r"x")',
        "axes = Axes(x_range=[0,1], include_numbers=True)",
        "import manimlib",
    ],
)
def test_validator_rejects_each_forbidden_construct(
    make_scene: Callable[..., SceneContract], violation: str
) -> None:
    # Arrange — each is a construct the no-LaTeX / CE-only rules forbid.
    bad = _VALID_SOURCE.replace('title = title_bar("Sorting")', f"bad = {violation}")

    # Act / Assert
    with pytest.raises(ValueError):
        validate_scene_source(bad, make_scene(1, "problem"))


def test_validator_rejects_missing_style_import(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange / Act / Assert — hardcoded literals instead of tokens must not pass.
    with pytest.raises(ValueError):
        validate_scene_source(
            _VALID_SOURCE.replace("from style_tokens import *\n", ""), make_scene(1, "problem")
        )


def test_validator_rejects_wrong_class_name(make_scene: Callable[..., SceneContract]) -> None:
    # Arrange / Act / Assert — the renderer selects by class name; drift = silent no-render.
    with pytest.raises(ValueError):
        validate_scene_source(
            _VALID_SOURCE.replace("S1Problem", "WrongName"), make_scene(1, "problem")
        )


def test_validator_normalizes_smart_quotes_that_would_break_parsing(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — the model used typographic (curly) double-quotes as string delimiters; Python
    # rejects them ("invalid character U+201C"). Normalize before compile, not via a wasted repair
    # turn (the prod S1_hook smart-quote failure). Built with chr() so this source stays ASCII.
    ldq, rdq = chr(0x201C), chr(0x201D)  # left / right double quotation marks
    smart = _VALID_SOURCE.replace('title_bar("Sorting")', f"title_bar({ldq}Sorting{rdq})")

    # Act — without normalization this raises ValueError("does not parse"); with it it passes.
    result = validate_scene_source(smart, make_scene(1, "problem"))

    # Assert — the smart quotes are gone, replaced by straight ASCII quotes that parse.
    assert ldq not in result and rdq not in result
    assert 'title_bar("Sorting")' in result


def test_validator_normalizes_em_en_dash_and_ellipsis(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — typographic dashes/ellipsis the model emits (here in a comment): a literal em-dash
    # in code position is a SyntaxError, so normalize all of them everywhere, deterministically.
    # Built with chr() so this test's own source stays ASCII.
    em, en, ellipsis = chr(0x2014), chr(0x2013), chr(0x2026)
    smart = _VALID_SOURCE.replace(
        "self.play(FadeIn(title))",
        f"self.play(FadeIn(title))  # step 1 {em} setup {en} then {ellipsis}",
    )

    # Act
    result = validate_scene_source(smart, make_scene(1, "problem"))

    # Assert — em-dash, en-dash and ellipsis are normalized to ASCII.
    assert all(ch not in result for ch in (em, en, ellipsis))
    assert "step 1 - setup - then ..." in result


@pytest.mark.parametrize(
    "codepoint, replacement",
    [
        (0x2014, "-"),  # em dash
        (0x2013, "-"),  # en dash
        (0x2012, "-"),  # figure dash
        (0x2018, "'"),  # left single quote
        (0x2019, "'"),  # right single quote
        (0x201C, '"'),  # left double quote
        (0x201D, '"'),  # right double quote
        (0x2026, "..."),  # ellipsis
        (0x00A0, " "),  # no-break space
    ],
)
def test_validator_normalizes_each_smart_codepoint(
    make_scene: Callable[..., SceneContract], codepoint: int, replacement: str
) -> None:
    # Arrange — every codepoint in the normalization table is replaced with its ASCII form (built
    # with chr() so this test's own source stays ASCII). Placed in a comment, valid either way, so
    # the assertion isolates the normalization, not a parse side effect.
    smart = _VALID_SOURCE.replace("clear_scene(self)", f"clear_scene(self)  # a{chr(codepoint)}b")

    # Act
    result = validate_scene_source(smart, make_scene(1, "problem"))

    # Assert
    assert chr(codepoint) not in result
    assert f"a{replacement}b" in result


def test_validator_rejects_unparseable_source(make_scene: Callable[..., SceneContract]) -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValueError):
        validate_scene_source("def broken(:\n    pass", make_scene(1, "problem"))


def test_validator_rejects_oversized_source(make_scene: Callable[..., SceneContract]) -> None:
    # Arrange — a degenerate completion far past any real scene (defense-in-depth before compile()).
    bloated = _VALID_SOURCE + "# " + "x" * 300_000 + "\n"

    # Act / Assert
    with pytest.raises(ValueError, match="exceeds"):
        validate_scene_source(bloated, make_scene(1, "problem"))
