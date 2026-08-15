import re
from urllib.parse import urlparse

from pydantic import Field, field_validator

from ...graph.schema.base import LiveModel

#: Absolute schemes a simulator may be loaded over.
#:
#: The *host* is deliberately unrestricted: Phase 3 may build simulators to a CDN, and an allow-list
#: of hosts is a deployment fact this contract does not have. What contains a hostile document is
#: the frame's sandbox — `allow-scripts` with no `allow-same-origin`, so it runs on an opaque origin
#: and can reach nothing of ours — and the fact that the worst it can do is fabricate an answer for
#: its own learner, which that learner could type anyway.
_MOUNTABLE_SCHEMES = frozenset({"http", "https"})

#: A same-origin path, by allow-list rather than by exclusion.
#:
#: Every character here is one RFC 3986 permits in a path, query or fragment. Written this way round
#: on purpose: the interesting failures in this guard are all characters a *browser* normalises and
#: ``urlparse`` does not, and enumerating those is a list that is only ever one entry short.
#: Backslash is the one that got through the first version — ``/\evil.com`` parses in Python as an
#: inert same-origin path and resolves in a browser to ``https://evil.com/``, because the URL spec
#: folds backslashes into slashes for http(s). An allow-list closes that whole class at once, and it
#: refuses the next member of it without anybody having to have heard of it.
#:
#: The leading ``(?!/)`` refuses the protocol-relative form, which is the same trick spelt with the
#: character that *is* allowed.
_SAFE_PATH = re.compile(r"\A/(?!/)[A-Za-z0-9\-._~/%?#\[\]@!$&'()*+,;=]*\Z")


def _is_mountable(url: str) -> bool:
    """Whether a frame may load this, checked at the contract rather than in a renderer.

    A registry entry is *data*, and Phase 3's registry is written by a builder agent — so
    ``javascript:`` and ``data:`` are refused here, where there is one place to keep it right,
    rather than in whichever renderer happens to read it. Both are script running with whatever the
    frame is trusted with.

    Root-relative paths are allowed and are what the stub uses: the API composing a session does not
    reliably know the origin a browser reached it on, and a same-origin path needs no such guess.
    They are matched against ``_SAFE_PATH`` rather than merely inspected, because "looks
    same-origin to Python" and "is same-origin to a browser" are not the same question — see the
    constant for the shape that proved it.
    """
    parsed = urlparse(url)
    if parsed.scheme:
        return parsed.scheme.lower() in _MOUNTABLE_SCHEMES
    # ``netloc`` as well as the pattern: belt and braces at the one seam where being wrong is
    # silently loading somebody else's page inside a lesson.
    return bool(_SAFE_PATH.fullmatch(url)) and not parsed.netloc


class SimApp(LiveModel):
    """A simulator the registry knows about, and where to load it from.

    Deliberately a *reference*, not a bundle. What Phase 3's factory builds is a self-contained
    interactive app (plan §9); what the loop needs to know about it is its identity, somewhere to
    mount it from, and what to call it. Keeping the loop on this side of that line is what lets the
    factory change everything about how sims are built without touching the socket.
    """

    #: Stable identity, so a session's history says which simulator a learner actually used even
    #: after the registry has rebuilt it somewhere else.
    app_id: str = Field(min_length=1, max_length=100)
    #: Where the frame loads it from — an ``http(s)`` URL or a root-relative, same-origin path.
    url: str = Field(min_length=1, max_length=500)
    #: What to call it on screen. The learner is being sent somewhere; an unlabelled frame is a
    #: black box appearing mid-lesson.
    title: str = Field(min_length=1, max_length=200)

    @field_validator("url")
    @classmethod
    def _loads_over_something_a_frame_may_run(cls, url: str) -> str:
        if not _is_mountable(url):
            raise ValueError(f"a simulator cannot be mounted from {url[:60]!r}")
        return url
