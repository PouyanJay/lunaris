"""The capability table marks which keyless fallbacks run on the local model-inference server (the
GPU/CPU-bound one) — only those carry a compute badge in the Draft UI."""

from lunaris_runtime.capabilities import CAPABILITY_SPECS
from lunaris_runtime.schema import CapabilityName


def test_only_the_llm_runs_on_local_inference() -> None:
    by_name = {spec.capability: spec for spec in CAPABILITY_SPECS}

    # The LLM fallback is the GPU/CPU-acceleratable local model server (carries a compute badge).
    assert by_name[CapabilityName.LLM].runs_on_local_inference is True
    # Embeddings is a separate CPU service; search/video are web services — no compute badge.
    assert by_name[CapabilityName.EMBEDDINGS].runs_on_local_inference is False
    assert by_name[CapabilityName.SEARCH].runs_on_local_inference is False
    assert by_name[CapabilityName.VIDEO].runs_on_local_inference is False
