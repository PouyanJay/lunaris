from dataclasses import dataclass

from lunaris_runtime.schema import CoverProvenance


@dataclass(frozen=True)
class RenderedCover:
    """What the cover pipeline produces: the finished image(s) plus their structural provenance.

    ``image`` is the raw PNG bytes of the DARK cover the worker uploads to the private
    ``course-covers`` bucket; ``content_type`` is its MIME type (``image/png`` today).
    ``image_light`` is the LIGHT-theme rendition of the same cover (dual-theme), or ``None`` when
    only the dark variant was produced (the re-theme was skipped or exhausted its QA budget) — the
    worker uploads it as a second object only when present, and ``provenance.has_light_variant``
    mirrors whether it is.
    ``provenance`` is the CLAUDE.md structural record — built at the source (the pipeline, once the
    image passes Claude vision-QA) and carried untouched through worker → storage → API.
    """

    image: bytes
    provenance: CoverProvenance
    image_light: bytes | None = None
    content_type: str = "image/png"
