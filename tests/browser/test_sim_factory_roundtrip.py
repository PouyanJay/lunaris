"""The real factory repairs model output only after the isolated browser rejects its behavior."""

import base64
import json
from importlib.resources import files
from pathlib import Path

import pytest
from lunaris_live.graph.schema import ConceptNode, MasteryCriterion
from lunaris_live.sims.container_verifier import ContainerSimVerifier
from lunaris_live.sims.factory import SimFactory
from lunaris_live.sims.models.completion import SimCompletion
from lunaris_live.sims.reference_app import reference_app
from lunaris_live.sims.schema.teaching_spec import TeachingCase, TeachingSpec

pytestmark = pytest.mark.browser
ROOT = Path(__file__).resolve().parents[2]


class _Model:
    model_name = "fixture-model"

    def __init__(self, replies):
        self.replies = iter(replies)
        self.images = []

    async def complete(self, prompt, *, max_tokens, images=None):
        self.images.append(images)
        return SimCompletion(text=json.dumps(next(self.replies)), model=self.model_name)


async def test_factory_repair_uses_real_browser_evidence(tmp_path):
    html = files("lunaris_live.sims").joinpath("reference.html").read_text()
    html = html.replace('id="x" type=', 'id="x" data-sim-param="x" type=')
    html = html.replace('id="y" for=', 'id="y" data-sim-output="y" for=')
    html = html.replace('id="ask" disabled', 'id="ask" data-sim-action="discuss" disabled')
    spec = TeachingSpec(
        contract=reference_app().contract,
        source="y=2x",
        source_version="1",
        cases=[TeachingCase(state={"x": x}, outputs={"y": f"y = {2 * x}"}) for x in (0, 4, 10)],
    )
    model = _Model(
        [
            {"spec": spec.model_dump(by_alias=True), "reason": "Exact relation"},
            {"html": html.replace("Number(x.value) * 2", "Number(x.value) * 3")},
            {"html": html},
            {"passed": True, "explanation": "Visible y is twice x."},
        ]
    )
    verifier = ContainerSimVerifier(
        image="lunaris-sim-verifier:test",
        seccomp=ROOT / "infra/sim-verifier/seccomp.json",
    )
    result = await SimFactory(model, verifier).build(
        ConceptNode(id="linear", name="Linear", definition="y = 2x"),
        MasteryCriterion(kind="manipulate", statement=spec.contract.objective, needs_sim=True),
        run_id="factory-browser",
    )
    assert model.images[:3] == [None, None, None]
    assert model.images[3] == result.reports[-1].screenshots
    assert len(model.images[3]) == 2
    assert all(
        base64.b64decode(image).startswith(b"\x89PNG\r\n\x1a\n") for image in model.images[3]
    )
    assert result.status == "approved"
    assert result.reason is None
    assert [report.approved for report in result.reports] == [False, True]
    assert result.bundle.candidate.html == html
    assert len(result.candidates) == 2
    assert result.bundle.report.content_hash == result.reports[-1].content_hash
    (tmp_path / "factory-result.json").write_text(result.model_dump_json(by_alias=True, indent=2))
