"""Measured container metadata must be present and structurally bounded."""

import struct
from pathlib import Path

import pytest
from lunaris_live.corpus.video.mp4_duration import mp4_duration


def box(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I4s", len(data) + 8, kind) + data


def media(duration: int = 12700, timescale: int = 1000) -> bytes:
    header = bytes(12) + struct.pack(">II", timescale, duration) + bytes(80)
    handler = bytes(8) + b"vide" + bytes(12)
    return box(b"ftyp", b"isom" + bytes(4)) + box(
        b"moov", box(b"mvhd", header) + box(b"trak", box(b"mdia", box(b"hdlr", handler)))
    )


def test_reads_real_container_clock_not_planned_timeline() -> None:
    assert mp4_duration(media()) == 12.7


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"garbage",
        media(timescale=0),
        media(duration=0),
        media()[:-2],
        media().replace(b"vide", b"soun"),
    ],
)
def test_malformed_or_non_video_container_rejected(data: bytes) -> None:
    with pytest.raises(ValueError):
        mp4_duration(data)


def test_version_one_64bit_clock_and_extended_size_box() -> None:
    header = b"\x01" + bytes(19) + struct.pack(">IQ", 1000, 12700) + bytes(80)
    handler = bytes(8) + b"vide" + bytes(12)
    movie = box(b"mvhd", header) + box(b"trak", box(b"mdia", box(b"hdlr", handler)))
    extended = struct.pack(">I4sQ", 1, b"moov", len(movie) + 16) + movie
    assert mp4_duration(box(b"ftyp", b"isom" + bytes(4)) + extended) == 12.7


@pytest.mark.parametrize(
    "suffix", [struct.pack(">I4s", 1, b"moov"), struct.pack(">I4sQ", 1, b"moov", 7)]
)
def test_invalid_extended_box_is_rejected(suffix: bytes) -> None:
    with pytest.raises(ValueError):
        mp4_duration(box(b"ftyp", b"isom") + suffix)


def test_duplicate_movie_metadata_and_fragmented_media_are_rejected() -> None:
    for content in (media() + media(), media() + box(b"moof", b"")):
        with pytest.raises(ValueError):
            mp4_duration(content)


def test_real_ffmpeg_output_matches_ffprobe(tmp_path: Path) -> None:
    import shutil
    import subprocess

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe required for real container comparison")
    target = tmp_path / "actual.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=16x16:r=10:d=1.3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(target),
        ],
        check=True,
        timeout=20,
        capture_output=True,
    )
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(target),
        ],
        check=True,
        timeout=10,
        capture_output=True,
        text=True,
    )
    assert mp4_duration(target.read_bytes()) == float(probe.stdout)
