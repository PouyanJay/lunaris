from dataclasses import dataclass

from lunaris_runtime.schema import CoverProvenance


@dataclass(frozen=True)
class RenderedCover:
    """What the cover pipeline produces: the finished image plus its structural provenance.

    ``image`` is the raw PNG bytes the worker uploads to the private ``course-covers`` bucket;
    ``content_type`` is its MIME type (``image/png`` today). ``provenance`` is the CLAUDE.md
    structural record — built at the source (the pipeline, once the image passes Claude vision-QA)
    and carried untouched through worker → storage → API.
    """

    image: bytes
    provenance: CoverProvenance
    content_type: str = "image/png"
