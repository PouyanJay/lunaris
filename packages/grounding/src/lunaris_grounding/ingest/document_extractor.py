from typing import Protocol

from lunaris_grounding.ingest.extracted_document import ExtractedDocument


class IDocumentExtractor(Protocol):
    """Extracts text from an uploaded file's bytes (P6.1 manual ingest).

    The file counterpart to the discovery ``IContentExtractor`` (which fetches + extracts a URL).
    Best-effort and never raises: ``None`` collapses every non-result — an unsupported type, a
    corrupt file, or one with no extractable text — into one "skip this source" signal.
    """

    async def extract(
        self, *, filename: str, content_type: str | None, data: bytes
    ) -> ExtractedDocument | None: ...
