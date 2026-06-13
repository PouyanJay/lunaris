"""SceneCodeGenerator tests (stubbed model): the deterministic source gate — no-LaTeX rule,
required class, style import, syntax — and the bounded format-repair loop around it."""

from collections.abc import Callable

import pytest
from _stubs import StubInvokeModel
from lunaris_video.codegen import SceneCodeGenerator, validate_scene_source
from lunaris_video.schemas import SceneContract

_VALID_SOURCE = """\
from manim import *
from style_tokens import *


class S1Problem(Scene):
    def construct(self):
        title = title_bar("Sorting")
        self.play(FadeIn(title))
        clear_scene(self)
"""


async def test_generate_returns_validated_source(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — the model wraps its code in fences; the validator strips them.
    stub = StubInvokeModel([f"```python\n{_VALID_SOURCE}```"])
    codegen = SceneCodeGenerator(invoke=stub)

    # Act
    source = await codegen.generate(make_scene(1, "problem"), topic="merge sort")

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
    await codegen.generate(scene, topic="merge sort")

    # Assert — the scene's contract JSON, the pinned no-pivot rule, and the exact class name
    # the renderer will select are all in the prompt.
    prompt = stub.prompts[0]
    assert scene.id in prompt
    assert "never rotate about get_center()" in prompt
    assert "class S1Problem(Scene):" in prompt


async def test_latex_in_a_completion_triggers_a_repair_turn(
    make_scene: Callable[..., SceneContract],
) -> None:
    # Arrange — first completion smuggles MathTex (the no-LaTeX rule's whole reason to exist).
    bad = _VALID_SOURCE.replace('title_bar("Sorting")', 'MathTex(r"\\frac{1}{2}")')
    stub = StubInvokeModel([bad, _VALID_SOURCE])
    codegen = SceneCodeGenerator(invoke=stub)

    # Act
    source = await codegen.generate(make_scene(1, "problem"), topic="merge sort")

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

    # Act
    await codegen.repair(
        make_scene(1, "problem"),
        source=failing_source,
        error_tail="NameError: name 'FadeInFrom' is not defined",
    )

    # Assert — the model sees exactly what failed and how.
    prompt = stub.prompts[0]
    assert "FadeInFrom" in prompt
    assert "NameError" in prompt


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


def test_validator_rejects_unparseable_source(make_scene: Callable[..., SceneContract]) -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValueError):
        validate_scene_source("def broken(:\n    pass", make_scene(1, "problem"))
