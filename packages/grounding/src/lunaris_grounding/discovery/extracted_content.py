from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedContent:
    """Clean main-text extracted from a fetched page (P7.2 discovery).

    A transient domain object (frozen dataclass, not a schema): the boilerplate-stripped article
    text a distillation step reads, tagged with its ``url`` so provenance can be constructed at the
    point of acquisition. ``title`` is best-effort.
    """

    url: str
    text: str
    title: str = ""
