"""The capability table marks which keyless fallbacks run on the local model-inference server (the
GPU/CPU-bound one) — only those carry a compute badge in the Draft UI."""

from lunaris_runtime.capabilities import CAPABILITY_SPECS
from lunaris_runtime.schema import CapabilityName


def test_only_the_llm_runs_on_local_inference() -> None:
    by_name = {spec.capability: spec for spec in CAPABILITY_SPECS}

    # The LLM fallback is the GPU/CPU-acceleratable local model server (carries a compute badge).
    assert by_name[CapabilityName.LLM].runs_on_local_inference is True
    # Embeddings is a separate CPU service; search/video/cover are web/API services — no badge.
    assert by_name[CapabilityName.EMBEDDINGS].runs_on_local_inference is False
    assert by_name[CapabilityName.SEARCH].runs_on_local_inference is False
    assert by_name[CapabilityName.VIDEO].runs_on_local_inference is False
    assert by_name[CapabilityName.COVER].runs_on_local_inference is False


def test_cover_capability_is_live_badge_only_openai_to_typographic() -> None:
    # The AI cover: live = OpenAI (the openai secret / OPENAI_API_KEY), fallback = Typographic.
    by_name = {spec.capability: spec for spec in CAPABILITY_SPECS}
    cover = by_name[CapabilityName.COVER]
    assert cover.secret_id == "openai" and cover.env_var == "OPENAI_API_KEY"
    assert cover.live_label == "OpenAI" and cover.fallback_label == "Typographic"
    # Surfaced on the live settings badge, but NOT a per-course build tag (covers generate async).
    assert cover.build_tagged is False


def test_only_cover_is_excluded_from_the_per_course_build_tag() -> None:
    # Every build leg is tagged; the cover (async, post-build) is the one intentional exclusion.
    not_tagged = {spec.capability for spec in CAPABILITY_SPECS if not spec.build_tagged}
    assert not_tagged == {CapabilityName.COVER}
