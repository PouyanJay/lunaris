from dataclasses import dataclass


@dataclass(frozen=True)
class RenderedVideo:
    """A pipeline's finished artifacts, in memory — what the worker uploads.

    Internal domain type: never serialized over the wire — the wire carries storage paths and
    signed URLs, not bytes.
    """

    mp4: bytes
    poster: bytes
