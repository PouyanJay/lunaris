from importlib.resources import files

from lunaris_live.sims.protocols.verifier import ISimVerifier
from lunaris_live.sims.reference_app import reference_app
from lunaris_live.sims.schema.candidate import SimCandidate
from lunaris_live.sims.schema.teaching_spec import TeachingCase, TeachingSpec


async def verify_worker_environment(verifier: ISimVerifier) -> None:
    """Prove the deployed Docker/Chromium boundary before admitting paid work."""
    html = files("lunaris_live.sims").joinpath("reference.html").read_text()
    html = (
        html.replace('id="x" type=', 'id="x" data-sim-param="x" type=')
        .replace('id="y" for=', 'id="y" data-sim-output="y" for=')
        .replace('id="ask" disabled', 'id="ask" data-sim-action="discuss" disabled')
    )
    spec = TeachingSpec(
        contract=reference_app().contract,
        source="supervisor startup: y=2x",
        source_version="1",
        cases=[TeachingCase(state={"x": x}, outputs={"y": f"y = {2 * x}"}) for x in (2, 4, 0)],
    )
    good = await verifier.verify(SimCandidate(html=html), spec)
    if not good.approved:
        raise RuntimeError("Verifier startup failed its behavior check")
    bad = await verifier.verify(
        SimCandidate(html=html + "<script>fetch('https://example.invalid/')</script>"), spec
    )
    if bad.approved:
        raise RuntimeError("Verifier startup accepted network access")
