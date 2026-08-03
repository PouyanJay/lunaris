"""Cost-metering coverage for the cover paid seam (course-cost-metering, T6).

GPT-Image runs in the cover worker (which enters a cost_scope in _render), so metering is a
``record_cost`` in the image adapter. This drives the real ``OpenAiImageRenderer`` via an injected
fake OpenAI client inside a ``cost_scope`` and asserts the recorded provider / unit.
"""

import base64
from types import SimpleNamespace

import pytest
from lunaris_covers.rendering.openai_image_renderer import COVER_IMAGE_MODEL, OpenAiImageRenderer
from lunaris_runtime.metering import CostScope, cost_scope
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostPocket, CostProvider, CostSubjectType


def _scope() -> CostScope:
    return CostScope(
        run_id="r",
        subject_type=CostSubjectType.COURSE,
        subject_id="c",
        price_book=PriceBook.current(),
    )


def _image_response() -> SimpleNamespace:
    return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(b"PNG").decode())])


class _FakeImages:
    async def generate(self, **kwargs: object) -> SimpleNamespace:
        return _image_response()

    async def edit(self, **kwargs: object) -> SimpleNamespace:
        return _image_response()


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.images = _FakeImages()


async def test_render_records_one_image_cost() -> None:
    renderer = OpenAiImageRenderer(client_factory=_FakeOpenAIClient)
    scope = _scope()
    with cost_scope(scope):
        await renderer.render("a cover of graphs")
    entry = scope.entries[0]
    assert entry.provider is CostProvider.OPENAI
    assert entry.model == COVER_IMAGE_MODEL
    assert entry.component == "cover_image"
    assert entry.usage == {"images": 1}
    assert entry.amount == pytest.approx(0.30)  # one gpt-image-2 render
    assert entry.pocket is CostPocket.PLATFORM  # no tenant OpenAI key in scope


async def test_retheme_records_a_second_image_cost() -> None:
    # The dual-theme light variant is a second billed image (edit endpoint).
    renderer = OpenAiImageRenderer(client_factory=_FakeOpenAIClient)
    scope = _scope()
    with cost_scope(scope):
        await renderer.render("dark cover")
        await renderer.retheme(b"PNG", instruction="light palette")
    assert [e.usage for e in scope.entries] == [{"images": 1}, {"images": 1}]
    assert all(e.provider is CostProvider.OPENAI for e in scope.entries)
