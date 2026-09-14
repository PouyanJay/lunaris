import re


def validate_pcm(key: str, pcm: bytes | None = None) -> None:
    if not re.fullmatch(r"[a-f0-9]{32}\.pcm", key):
        raise ValueError("Invalid private voice object key")
    if pcm is not None and (not 2 <= len(pcm) <= 11_520_000 or len(pcm) % 2):
        raise ValueError("Invalid generated PCM size")
