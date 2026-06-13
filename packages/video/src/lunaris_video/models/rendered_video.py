from dataclasses import dataclass


@dataclass(frozen=True)
class RenderedVideo:
    """A pipeline's finished artifacts, in memory — what the worker uploads.

    Internal domain type: never serialized over the wire — the wire carries storage paths and
    signed URLs, not bytes. Beyond the playable ``mp4`` + ``poster``, the bundle carries the two
    artifacts regeneration really needs (plan §8.2): ``contracts_json`` (the regeneration-stable
    plan) and ``timing_json`` (the silent-but-voice-ready manifest V3 swaps measured timings into).
    """

    mp4: bytes
    poster: bytes
    contracts_json: bytes
    timing_json: bytes
