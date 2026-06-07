from lunaris_grounding import host

# The YouTube hosts a watchable video can arrive on. `host()` already strips a leading ``www.`` and
# the port, so the bare registrable forms are enough; ``youtu.be`` is the short-link domain.
_YOUTUBE_HOSTS: frozenset[str] = frozenset(
    {"youtube.com", "m.youtube.com", "youtube-nocookie.com", "youtu.be"}
)


def is_youtube_url(url: str) -> bool:
    """True when ``url`` points at a YouTube video host — the signal that a result is a video no
    matter what kind the query asked for. Mirrors the web reader's ``youTubeId`` host set so the two
    layers agree on what counts as a playable video."""
    return host(url) in _YOUTUBE_HOSTS
