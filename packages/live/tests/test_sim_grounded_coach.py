import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from lunaris_live.session import TutorUnavailableError
from lunaris_live.sims.grounded_coach import GroundedSimCoach
from lunaris_live.sims.models.completion import SimCompletion
from lunaris_live.sims.registry.schema.asset import SimAsset
from lunaris_live.sims.schema.event import SimEvent

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("state", [{"x": 0}, {"x": 99}])
async def test_coach_uses_approved_teaching_cases_and_rejects_invalid_commands(state):
    raw = json.loads(
        (
            ROOT / "documentation/evaluations/live-sim-builder-2026-09-11/approved-result.json"
        ).read_text()
    )
    owner = str(uuid4())
    asset = SimAsset(
        id=uuid4(), owner_id=owner, cache_key="a" * 64, bundle=raw["bundle"], calls=raw["calls"]
    )
    store = Mock()
    store.load.return_value = asset
    model = Mock()
    model.complete = AsyncMock(
        return_value=SimCompletion(
            text=json.dumps({"text": "Compare this with the origin.", "state": state}),
            model="fixture",
            input_tokens=1,
            output_tokens=1,
        )
    )
    coach = GroundedSimCoach(model, store, owner_id=owner)
    event = SimEvent(
        version=1,
        instance_id="turn",
        turn_seq=1,
        sequence=1,
        app_id=str(asset.id),
        kind="param_changed",
        state={"x": 4},
    )
    if state["x"] > 10:
        with pytest.raises(TutorUnavailableError):
            await coach.respond(asset.bundle.spec.contract, event, run_id="run")
    else:
        result = await coach.respond(asset.bundle.spec.contract, event, run_id="run")
        assert result.state == state
    prompt = model.complete.call_args.args[0]
    assert asset.bundle.spec.source in prompt
    assert '"x": 4.0' in prompt
    assert '"outputs"' in prompt
    assert model.complete.call_args.kwargs["max_tokens"] == 700
    store.load.assert_called_once_with(str(asset.id), owner_id=owner)
