"""Each concurrent model call preserves its own measured cost and actual model identity."""

import asyncio
from types import SimpleNamespace

from lunaris_live.sims.claude_model import ClaudeSimModel
from lunaris_runtime.metering.cost_entry import CostEntry
from lunaris_runtime.metering.cost_scope import CostScope, cost_scope, current_cost_scope
from lunaris_runtime.pricing import PriceBook
from lunaris_runtime.schema import CostPocket, CostProvider, CostSubjectType


async def test_concurrent_completions_have_isolated_cost_and_actual_provider_identity(monkeypatch):
    entered = 0
    both_entered = asyncio.Event()

    class Client:
        model_name = "actual-local-model"
        max_retries = 2

        def bind(self, **kwargs):
            assert kwargs["max_tokens"] == 300
            assert self.max_retries == 0
            return self

        async def ainvoke(self, prompt):
            nonlocal entered
            entered += 1
            if entered == 2:
                both_entered.set()
            await both_entered.wait()
            current_cost_scope().entries.append(
                CostEntry(
                    component="live.sim.factory",
                    provider=CostProvider.LOCAL,
                    model=self.model_name,
                    usage={},
                    amount=float(prompt),
                    pocket=CostPocket.PLATFORM,
                )
            )
            return SimpleNamespace(
                content="{}", usage_metadata={"input_tokens": 5, "output_tokens": 2}
            )

    monkeypatch.setattr(
        "lunaris_live.sims.claude_model.build_chat_model", lambda *a, **kw: Client()
    )
    scope = CostScope(
        run_id="costs",
        subject_type=CostSubjectType.LIVE_GRAPH,
        subject_id="g",
        price_book=PriceBook.current(),
    )
    model = ClaudeSimModel("requested-provider-model")
    with cost_scope(scope):
        first, second = await asyncio.gather(
            model.complete("1", max_tokens=300),
            model.complete("2", max_tokens=300),
        )
        assert current_cost_scope() is scope
    assert (first.cost_usd, second.cost_usd) == (1, 2)
    assert first.model == second.model == "actual-local-model"
    assert sum(entry.amount for entry in scope.entries) == 3


async def test_visual_evidence_reaches_provider_as_image_content(monkeypatch):
    messages = []

    class Client:
        max_retries = 2

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, message):
            messages.append(message)
            return SimpleNamespace(content="{}", usage_metadata={})

    monkeypatch.setattr(
        "lunaris_live.sims.claude_model.build_chat_model", lambda *a, **kw: Client()
    )
    await ClaudeSimModel("vision").complete(
        "Review the chart", max_tokens=1500, images=["first", "second"]
    )
    assert messages == [
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Review the chart"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,first"}},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,second"}},
                ],
            }
        ]
    ]
