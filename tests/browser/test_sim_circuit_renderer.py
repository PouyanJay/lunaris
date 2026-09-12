"""A real numeric app with a factory-assembled circuit; geometry is independently checked."""

from pathlib import Path

import pytest
from lunaris_live.sims.container_verifier import ContainerSimVerifier
from lunaris_live.sims.schema.candidate import SimCandidate
from lunaris_live.sims.schema.teaching_spec import TeachingSpec
from lunaris_live.sims.series_circuit_renderer import SeriesCircuitRenderer

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.browser
HTML = """<!doctype html><html><body>
<label>Voltage<input data-sim-param="voltage" id="v" type="number" value="6"></label>
<label>Resistance<input data-sim-param="resistance" id="r" type="number" value="3"></label>
<output data-sim-output="current" id="out"></output>
<button data-sim-action="discuss" id="ask">Discuss</button>
<div data-lunaris-renderer="series-resistor-v1"></div>
<script>
const v=document.getElementById('v'),r=document.getElementById('r');
const o=document.getElementById('out');
let appId,instanceId;function draw(){o.textContent=(Number(v.value)/Number(r.value)).toFixed(2)}
function state(){return {voltage:Number(v.value),resistance:Number(r.value)}}
v.oninput=r.oninput=draw;
window.addEventListener('message',e=>{const d=e.data;if(d.version!==1)return;
if(d.type==='lunaris.sim.init'){appId=d.appId;instanceId=d.instanceId}
if(d.state){v.value=d.state.voltage;r.value=d.state.resistance;draw()}
if(d.type==='lunaris.sim.availability')document.getElementById('ask').disabled=!d.active});
document.getElementById('ask').onclick=()=>parent.postMessage({type:'lunaris.sim.event',version:1,
appId,instanceId,kind:'param_changed',state:state()},'*');draw();
parent.postMessage({type:'lunaris.sim.ready',version:1},'*');
</script></body></html>"""


def _spec():
    return TeachingSpec.model_validate(
        {
            "contract": {
                "objective": "Explore current through one ideal series resistor.",
                "parameters": {
                    "voltage": {"label": "V", "minimum": 0, "maximum": 12, "step": 1, "default": 6},
                    "resistance": {
                        "label": "R",
                        "minimum": 1,
                        "maximum": 6,
                        "step": 1,
                        "default": 3,
                    },
                },
            },
            "source": "I=V/R",
            "sourceVersion": "1",
            "cases": [
                {"state": {"voltage": 0, "resistance": 1}, "outputs": {"current": "0.00"}},
                {"state": {"voltage": 6, "resistance": 3}, "outputs": {"current": "2.00"}},
                {"state": {"voltage": 12, "resistance": 2}, "outputs": {"current": "6.00"}},
            ],
        }
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "good",
        "source_bypass",
        "missing_wire",
        "hidden",
        "invisible_wire",
        "moved_resistor",
        "untagged_bypass",
    ],
)
async def test_assembled_circuit_has_real_source_and_resistor_connections(mutation):

    html = SeriesCircuitRenderer().assemble(HTML, _spec())
    if mutation == "hidden":
        html += "<style>[data-lunaris-renderer]{display:none}</style>"
    elif mutation != "good":
        action = (
            "s.querySelector('[data-circuit-wire]').remove()"
            if mutation == "missing_wire"
            else "const l=document.createElementNS('http://www.w3.org/2000/svg','line');"
            "for(const[k,v]of Object.entries({'data-circuit-wire':'',"
            "x1:80,y1:135,x2:80,y2:165,stroke:'black'}))l.setAttribute(k,v);"
            "s.querySelector('svg').append(l)"
        )
        if mutation == "untagged_bypass":
            action = action.replace("'data-circuit-wire':'',", "")
        if mutation == "invisible_wire":
            action = "s.querySelector('[data-circuit-wire]').style.visibility='hidden'"
        if mutation == "moved_resistor":
            action = (
                "s.querySelector('[data-circuit-resistor]')"
                ".setAttribute('transform','translate(100 0)')"
            )
        html += (
            "<script>document.addEventListener('input',()=>{"
            "const s=document.querySelector('[data-lunaris-renderer]').shadowRoot;"
            + action
            + "});</script>"
        )
    checked = await ContainerSimVerifier(
        image="lunaris-sim-verifier:test", seccomp=ROOT / "infra/sim-verifier/seccomp.json"
    ).verify(SimCandidate(html=html), _spec())
    assert checked.approved is (mutation == "good"), checked.reasons


async def test_voltage_resistance_contract_requires_assembled_circuit():
    checked = await ContainerSimVerifier(
        image="lunaris-sim-verifier:test", seccomp=ROOT / "infra/sim-verifier/seccomp.json"
    ).verify(SimCandidate(html=HTML.replace(SeriesCircuitRenderer.marker, "")), _spec())
    assert not checked.approved
    assert "assembled circuit" in " ".join(checked.reasons)
