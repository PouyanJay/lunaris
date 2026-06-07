"""Recognise a YouTube video URL — the signal that a curated result is a video regardless of the
kind its query asked for. Kept in lock-step with the web reader's ``youTubeId`` host set so both
layers agree on what counts as a playable video."""

from lunaris_grounding import host

# The YouTube hosts a watchable video can arrive on. `host()` already strips a leading ``www.`` and
# the port, so the bare registrable forms are enough; ``youtu.be`` is the short-link domain. Note
# ``host()`` strips only ``www.`` — the ``m.`` mobile subdomain is retained, so it must stay listed.
_YOUTUBE_HOSTS: frozenset[str] = frozenset(
    {"youtube.com", "m.youtube.com", "youtube-nocookie.com", "youtu.be"}
)


def is_youtube_url(url: str) -> bool:
    """True when ``url`` points at a YouTube video host — the signal that a result is a video no
    matter what kind the query asked for. Mirrors the web reader's ``youTubeId`` host set so the two
    layers agree on what counts as a playable video."""
    return host(url) in _YOUTUBE_HOSTS
