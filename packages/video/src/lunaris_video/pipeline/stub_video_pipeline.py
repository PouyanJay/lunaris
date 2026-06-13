from datetime import UTC, datetime
from importlib import resources

from lunaris_runtime.schema import VideoJob, VideoProvenance

from lunaris_video.models.rendered_video import RenderedVideo

# Minimal but valid regeneration artifacts so the stub exercises the same five-artifact upload
# path the real pipeline does — the walking skeleton stays honest end to end.
_STUB_CONTRACTS_JSON = b'{"topic": "stub", "scenes": []}'
_STUB_TIMING_JSON = b"{}"


class StubVideoPipeline:
    """The walking skeleton's pipeline: returns packaged placeholder media, renders nothing.

    The assets are a real 2-second MP4 and a real JPEG poster (generated once with ffmpeg and
    committed), so every downstream layer — storage, signed URLs, the reader's player — handles
    honest media from day one. V1 swaps this for ``LessonVideoPipeline`` behind ``IVideoPipeline``.
    """

    async def produce(self, job: VideoJob) -> RenderedVideo:
        assets = resources.files("lunaris_video") / "assets"
        return RenderedVideo(
            mp4=(assets / "stub.mp4").read_bytes(),
            poster=(assets / "poster.jpg").read_bytes(),
            contracts_json=_STUB_CONTRACTS_JSON,
            timing_json=_STUB_TIMING_JSON,
            provenance_json=_stub_provenance(job),
        )


def _stub_provenance(job: VideoJob) -> bytes:
    """A stub video still carries real provenance — the spine asserts nothing it can't trace."""
    provenance = VideoProvenance(
        job_id=job.id,
        course_id=job.course_id,
        lesson_id=job.lesson_id,
        kind=job.kind,
        model="stub",
        contract_hash="stub",
        input_hash=job.input_hash,
        claim_ids=[],
        generated_at=datetime.now(UTC).isoformat(),
    )
    return provenance.model_dump_json(by_alias=True).encode()
