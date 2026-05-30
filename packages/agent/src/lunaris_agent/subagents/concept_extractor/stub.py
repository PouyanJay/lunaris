from .extraction import Extraction


class StubConceptExtractor:
    """Returns a preconfigured extraction. Lets the pipeline be tested without a model."""

    def __init__(self, extraction: Extraction) -> None:
        self._extraction = extraction

    async def extract(self, topic: str) -> Extraction:
        return self._extraction
