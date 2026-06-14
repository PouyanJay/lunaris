from dataclasses import dataclass, field

from lunaris_runtime.schema import DegradedScene


@dataclass(frozen=True)
class RenderedVideo:
    """A pipeline's finished artifacts, in memory — what the worker uploads.

    Internal domain type: never serialized over the wire — the wire carries storage paths and
    signed URLs, not bytes. Beyond the playable ``mp4`` + ``poster``, the bundle carries the two
    artifacts regeneration really needs (plan §8.2): ``contracts_json`` (the regeneration-stable
    plan) and ``timing_json`` (the silent-but-voice-ready manifest V3 swaps measured timings into).
    ``provenance_json`` is the serialized ``VideoProvenance`` built at the source (the pipeline sets
    it per produce, even on a cache hit, so it is always the requesting job's own); the worker
    uploads it and the API threads it onto the wire. ``None`` means a producer that built only the
    render artifacts (e.g. the assembler before the pipeline restamps) — absence is explicit, never
    a bogus empty artifact.
    """

    mp4: bytes
    poster: bytes
    contracts_json: bytes
    timing_json: bytes
    # WebVTT captions — present only for a narrated video (beats and measured timing); ``None`` for
    # a silent one, which has no audio to caption (plan principle 8). The player adds the track only
    # when this is present.
    captions: bytes | None = None
    provenance_json: bytes | None = None
    # Scenes Gate B shipped as best-effort (the 'publish anyway' degrade). Carried ON the bundle so
    # it survives the contract-hash cache — a later job that hits the cache reuses the SAME render,
    # so it must reuse the SAME degrade record (provenance stays honest across cache hits). Empty
    # when every scene passed QA cleanly.
    degraded_scenes: tuple[DegradedScene, ...] = field(default_factory=tuple)
