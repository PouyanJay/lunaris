import asyncio
from pathlib import Path

import structlog

from lunaris_video.assembly.caption_builder import build_webvtt
from lunaris_video.errors import VideoPipelineError
from lunaris_video.models.rendered_scene import RenderedScene
from lunaris_video.models.rendered_video import RenderedVideo
from lunaris_video.rendering.sandbox import run_sandboxed
from lunaris_video.schemas import TimingManifest, VideoContract

_logger = structlog.get_logger(__name__)

_CONCAT_TIMEOUT_S = 120.0
_POSTER_TIMEOUT_S = 60.0
_AUDIO_TIMEOUT_S = 180.0  # covers both the mix (build the track) and the mux (overlay it)
_AUDIO_RATE = 44100

# The muxed (narrated) video the assembler writes into the workdir — the artifact Gate D inspects
# (it runs on the muxed video, after assembly). A shared name is the contract between the writer
# (this assembler) and the reader (the pipeline's Gate-D step), so neither passes a path around.
NARRATED_VIDEO_NAME = "narrated.mp4"


class VideoAssembler:
    """Stage 4: concat the cleared per-scene MP4s, mux narration when voiced, extract a poster, and
    bundle the regeneration artifacts.

    Concat is a stream-copy (``-c copy``): every scene shares the renderer's encoder settings, so
    the join needs no re-encode (the skill's calibration). When the manifest is voiced, the per-beat
    clips + computed silences are mixed into one audio track exactly as long as the video and muxed
    on (the audio-drives-video sync is already baked into the render, so the mux is a clean
    overlay), and WebVTT captions ship from beats and timing (free, WCAG 2.2 AA). The poster is the
    FINAL (muxed) video's first frame. ``timing.json`` is the SAME manifest that drove the render —
    persisted, never re-derived. ffmpeg runs in the hardened sandbox; scenes are untrusted codegen.
    """

    async def assemble(
        self,
        scenes: list[RenderedScene],
        contract: VideoContract,
        *,
        manifest: TimingManifest,
        workdir: Path,
        audio_dir: Path | None = None,
    ) -> RenderedVideo:
        if not scenes:
            raise VideoPipelineError("cannot assemble a video with no rendered scenes")
        silent_mp4 = workdir / "final.mp4"
        poster = workdir / "poster.jpg"
        await self._concat(scenes, silent_mp4, workdir=workdir)
        final_mp4, captions = await self._apply_narration(
            silent_mp4, contract, manifest, audio_dir, workdir=workdir
        )
        await self._extract_poster(final_mp4, poster)
        mp4_bytes, poster_bytes = await asyncio.gather(
            asyncio.to_thread(final_mp4.read_bytes), asyncio.to_thread(poster.read_bytes)
        )
        timing_json = manifest.model_dump_json(indent=2).encode()
        contracts_json = contract.model_dump_json(indent=2).encode()
        _logger.info(
            "video_assembler.assembled",
            scenes=len(scenes),
            mp4_bytes=len(mp4_bytes),
            narrated=manifest.is_voiced,
        )
        return RenderedVideo(
            mp4=mp4_bytes,
            poster=poster_bytes,
            contracts_json=contracts_json,
            timing_json=timing_json,
            captions=captions,
        )

    async def _concat(self, scenes: list[RenderedScene], final_mp4: Path, *, workdir: Path) -> None:
        # The concat demuxer reads a list file of `file '<path>'` lines; -safe 0 allows the
        # absolute per-scene paths (they live under media/, not beside the list).
        concat_list = workdir / "concat.txt"
        lines = "".join(f"file '{scene.mp4_path}'\n" for scene in scenes)
        await asyncio.to_thread(concat_list.write_text, lines, encoding="utf-8")
        argv = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list.name,
            "-c",
            "copy",
            final_mp4.name,
        ]
        result = await run_sandboxed(argv, cwd=workdir, timeout_s=_CONCAT_TIMEOUT_S)
        if not result.succeeded or not await asyncio.to_thread(final_mp4.is_file):
            raise VideoPipelineError(f"ffmpeg concat failed: {result.stderr_tail}")

    async def _apply_narration(
        self,
        silent_mp4: Path,
        contract: VideoContract,
        manifest: TimingManifest,
        audio_dir: Path | None,
        *,
        workdir: Path,
    ) -> tuple[Path, bytes | None]:
        """Voiced: mux the narration on and build captions, returning (narrated mp4, vtt). Silent:
        pass the concat through unchanged, returning (silent mp4, None)."""
        if not manifest.is_voiced:
            return silent_mp4, None
        if audio_dir is None:
            raise VideoPipelineError("a voiced manifest needs an audio_dir to mux narration")
        narrated_mp4 = workdir / NARRATED_VIDEO_NAME
        await self._mux_narration(silent_mp4, narrated_mp4, manifest, audio_dir, workdir=workdir)
        return narrated_mp4, build_webvtt(contract, manifest).encode()

    async def _mux_narration(
        self,
        silent_mp4: Path,
        narrated_mp4: Path,
        manifest: TimingManifest,
        audio_dir: Path,
        *,
        workdir: Path,
    ) -> None:
        """Mix the per-beat clips + computed silences into one track and mux it onto the video.

        Each beat occupies exactly its ``anim_s`` window (a clip padded to that length, or pure
        silence for a silent beat), concatenated in scene order — the same timeline the render was
        built against, so video and audio stay locked (the skill's deterministic sync)."""
        narration_wav = workdir / "narration.wav"
        await self._mix_audio(manifest, audio_dir, narration_wav, workdir=workdir)
        argv = [
            "ffmpeg", "-y", "-v", "error",
            "-i", silent_mp4.name,
            "-i", narration_wav.name,
            "-c:v", "copy", "-c:a", "aac",
            "-map", "0:v:0", "-map", "1:a:0", "-shortest",
            narrated_mp4.name,
        ]  # fmt: skip
        result = await run_sandboxed(argv, cwd=workdir, timeout_s=_AUDIO_TIMEOUT_S)
        if not result.succeeded or not await asyncio.to_thread(narrated_mp4.is_file):
            raise VideoPipelineError(f"ffmpeg narration mux failed: {result.stderr_tail}")

    async def _mix_audio(
        self, manifest: TimingManifest, audio_dir: Path, out_wav: Path, *, workdir: Path
    ) -> None:
        inputs: list[str] = []
        filters: list[str] = []
        labels: list[str] = []
        clip_index = 0
        for scene_id in manifest.scene_ids():
            for beat in manifest[scene_id].beats:
                segment = f"[s{len(labels)}]"
                if beat.audio:
                    # A clip padded with trailing silence to exactly its window. anim_s is
                    # max(audio_s + pad, floor) >= audio_s, so the clip always fits (never cut).
                    inputs += ["-i", str(audio_dir / beat.audio)]
                    filters.append(
                        f"[{clip_index}:a]aformat=sample_rates={_AUDIO_RATE}:channel_layouts=stereo,"
                        f"apad,atrim=0:{beat.anim_s}{segment}"
                    )
                    clip_index += 1
                else:
                    filters.append(
                        f"anullsrc=r={_AUDIO_RATE}:cl=stereo,atrim=0:{beat.anim_s}{segment}"
                    )
                labels.append(segment)
        # The filtergraph is the per-beat segments, then a concat filter that joins all of them, in
        # order, into one audio-only stream [out] (n = segment count, v=0 video, a=1 audio).
        graph = ";".join(filters) + f";{''.join(labels)}concat=n={len(labels)}:v=0:a=1[out]"
        argv = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph,
                "-map", "[out]", out_wav.name]  # fmt: skip
        result = await run_sandboxed(argv, cwd=workdir, timeout_s=_AUDIO_TIMEOUT_S)
        if not result.succeeded or not await asyncio.to_thread(out_wav.is_file):
            raise VideoPipelineError(f"ffmpeg narration mix failed: {result.stderr_tail}")

    async def _extract_poster(self, final_mp4: Path, poster: Path) -> None:
        argv = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            final_mp4.name,
            "-frames:v",
            "1",
            poster.name,
        ]
        result = await run_sandboxed(argv, cwd=final_mp4.parent, timeout_s=_POSTER_TIMEOUT_S)
        if not result.succeeded or not await asyncio.to_thread(poster.is_file):
            raise VideoPipelineError(f"ffmpeg poster extraction failed: {result.stderr_tail}")
