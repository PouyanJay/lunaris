from importlib import resources

from lunaris_runtime.schema import VideoJob

from lunaris_video.models.rendered_video import RenderedVideo

# Minimal but valid regeneration artifacts so the stub exercises the same four-artifact upload
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
        )
