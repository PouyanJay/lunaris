import struct
from collections.abc import Iterator


def mp4_duration(data: bytes) -> float:
    """Read the ISO-BMFF movie clock, requiring a video track and bounded box structure.

    Clock layout follows FFmpeg mov_read_mvhd:
    https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/mov.c

    This verifies container timing, not visual content. Unsupported/fragmented media with no
    finite movie duration is rejected; no duration is guessed from the planned transcript.
    """
    top = list(_boxes(memoryview(data)))
    kinds = [kind for kind, _ in top]
    if kinds.count(b"ftyp") != 1 or kinds.count(b"moov") != 1 or b"moof" in kinds:
        raise ValueError("unsupported or duplicate movie metadata")
    boxes = dict(top)
    if b"ftyp" not in boxes or b"moov" not in boxes:
        raise ValueError("missing MP4 metadata")
    movie = list(_boxes(boxes[b"moov"]))
    headers = [payload for kind, payload in movie if kind == b"mvhd"]
    if len(headers) != 1:
        raise ValueError("missing unique movie clock")
    header = headers[0]
    if not header:
        raise ValueError("empty movie clock")
    version = header[0]
    offset, width = (12, 4) if version == 0 else (20, 8)
    if version not in (0, 1) or len(header) < offset + 4 + width:
        raise ValueError("unsupported movie clock")
    scale = int.from_bytes(header[offset : offset + 4], "big")
    duration = int.from_bytes(header[offset + 4 : offset + 4 + width], "big")
    if not scale or not duration or duration == (1 << (8 * width)) - 1:
        raise ValueError("unknown movie duration")
    if not any(_video_track(payload) for kind, payload in movie if kind == b"trak"):
        raise ValueError("no video track")
    seconds = duration / scale
    if not 0 < seconds <= 14400:
        raise ValueError("unsupported movie duration")
    return seconds


def _video_track(track: memoryview) -> bool:
    for kind, payload in _boxes(track):
        if kind == b"mdia":
            for child, handler in _boxes(payload):
                if child == b"hdlr" and len(handler) >= 12 and handler[8:12] == b"vide":
                    return True
    return False


def _boxes(data: memoryview) -> Iterator[tuple[bytes, memoryview]]:
    offset = 0
    count = 0
    while offset < len(data):
        count += 1
        if count > 10000 or len(data) - offset < 8:
            raise ValueError("invalid MP4 box structure")
        size, kind = struct.unpack_from(">I4s", data, offset)
        header = 8
        if size == 1:
            if len(data) - offset < 16:
                raise ValueError("truncated extended box")
            size = struct.unpack_from(">Q", data, offset + 8)[0]
            header = 16
        elif size == 0:
            size = len(data) - offset
        if size < header or size > len(data) - offset:
            raise ValueError("invalid MP4 box size")
        yield kind, data[offset + header : offset + size]
        offset += size
