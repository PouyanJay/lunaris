from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedDocument:
    """Plain text extracted from an uploaded file (P6.1); ``title`` is the file stem."""

    text: str
    title: str = ""
