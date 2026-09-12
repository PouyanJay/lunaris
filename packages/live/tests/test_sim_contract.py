import pytest
from lunaris_live.sims.schema.parameter import SimParameter
from pydantic import ValidationError


@pytest.mark.parametrize(
    "updates", [{"default": 3}, {"maximum": 9}, {"step": float("nan")}, {"default": True}]
)
def test_contract_rejects_controls_that_cannot_initialize_or_reach_their_boundary(updates):
    fields = {"label": "x", "minimum": 0, "maximum": 10, "step": 2, "default": 2, **updates}
    with pytest.raises(ValidationError):
        SimParameter(**fields)
