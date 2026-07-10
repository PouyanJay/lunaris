import struct
import zlib
from datetime import UTC, datetime

from lunaris_runtime.schema import CoverJob, CoverJobStatus, CoverProvenance

from lunaris_covers.models.rendered_cover import RenderedCover
from lunaris_covers.protocols.cover_pipeline_protocol import StageReporter

# The house night-sky ground — a real (if trivial) image so the whole path carries genuine PNG
# bytes, not an empty placeholder. Replaced in Phase 2 by the GPT Image 2 render.
_NIGHT_SKY_RGB = (10, 12, 16)


def _solid_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """A minimal, valid solid-colour RGB PNG, built with only the stdlib (no Pillow).

    Enough to prove real image bytes flow queue → worker → storage → API → web without pulling an
    image library into the skeleton. The real cover is a GPT Image 2 render (Phase 2).
    """

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit, colour type 2 (RGB)
    row = b"\x00" + bytes(rgb) * width  # filter byte 0 (none) + the row's pixels
    idat = zlib.compress(row * height)
    return (
        b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")
    )


class StubCoverPipeline:
    """The walking-skeleton cover pipeline: a solid night-sky PNG, no OpenAI/Claude.

    Proves the queue → worker → storage → API → web path end to end before the real art-director +
    GPT Image 2 + vision-QA loop exists (Phase 2). It still reports the render stages and returns a
    populated ``CoverProvenance``, so the provenance contract is exercised from day one — every
    field just carries a ``"stub"`` marker instead of a real model id.
    """

    def __init__(self, *, width: int = 8, height: int = 8) -> None:
        self._width = width
        self._height = height

    async def produce(self, job: CoverJob, *, on_stage: StageReporter) -> RenderedCover:
        await on_stage(CoverJobStatus.RENDERING)
        image = _solid_png(self._width, self._height, _NIGHT_SKY_RGB)
        await on_stage(CoverJobStatus.QA)
        provenance = CoverProvenance(
            job_id=job.id,
            course_id=job.course_id,
            source="stub",
            model="stub",
            art_director_model="stub",
            qa_model="stub",
            style_preset=job.style_preset,
            prompt="(stub) walking-skeleton placeholder cover",
            qa_attempts=1,
            input_hash=job.input_hash,
            generated_at=datetime.now(UTC).isoformat(),
        )
        return RenderedCover(image=image, provenance=provenance)
