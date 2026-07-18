"""Sign display-size cover thumbnails for the library grid — covers ready in one request.

The course list used to ship only the cover HANDLE, so each card minted its own signed URL: N
follow-up ``GET /api/covers/{jobId}`` calls that resolved one by one (the "covers pop in one by
one" bug). Minting each READY cover's display-size ``thumb_url`` (+ its dual-theme light twin) here,
at list-query time and concurrently across the page, lets the whole grid arrive cover-ready in a
single request. The full-size master stays behind the per-job exchange (the reader's lightbox +
regenerate) — the list only ever needs the resized card thumb.
"""

import asyncio
from collections.abc import Coroutine, Sequence
from dataclasses import dataclass
from typing import Any

import structlog
from lunaris_runtime.persistence import CoverArtifactPaths, ICoverStorage, PersistenceError
from lunaris_runtime.schema import CoverJobStatus

from .cover_display_transform import COVER_DISPLAY_TRANSFORM
from .library import CourseSummary

logger = structlog.get_logger()

# Each READY cover costs one (or, dual-theme, two) outbound signed-URL calls, so a large library
# could otherwise fan out into a burst of concurrent Storage round trips on this hot endpoint. Cap
# the in-flight signs per request — the grid still arrives in one API round trip, just not with an
# unbounded outbound burst behind it.
_MAX_CONCURRENT_THUMB_SIGNS = 8


@dataclass(frozen=True)
class CoverThumbs:
    """A course's pre-signed display-size cover thumbs, dark and (dual-theme) light. Either URL is
    None when there is nothing to sign — no cover, a non-READY cover, or a storage backend that
    cannot resize (best effort) — and the card falls back to the master or the Typographic cover."""

    thumb_url: str | None = None
    thumb_url_light: str | None = None


async def mint_cover_thumb(storage: ICoverStorage, path: str) -> str | None:
    """The display-size derivative's signed URL — best effort.

    The resized derivative is an OPTIMIZATION (a sharp, ~20x lighter card image), not the cover
    itself: a storage backend that cannot resize — transformations disabled, a transform quota or
    hiccup — must degrade to ``None`` (the reader's ladder falls back to the master), never take
    down the read it rode in on. Only ``PersistenceError`` is caught, relying on the ``@guard``-
    wrapped storage to translate backend faults into it (as ``_cover_job_view`` also does)."""
    try:
        return await storage.signed_url(path=path, transform=COVER_DISPLAY_TRANSFORM)
    except PersistenceError as exc:
        logger.warning("cover_thumb_unavailable", path=path, reason=type(exc).__name__)
        return None


async def sign_library_cover_thumbs(
    storage: ICoverStorage, owner_id: str | None, summaries: Sequence[CourseSummary]
) -> dict[str, CoverThumbs]:
    """Pre-sign each READY cover's display-size thumb(s), keyed by course id.

    Minted concurrently across the whole page, so a library of N courses costs one round of parallel
    signs rather than N sequential per-card exchanges. The light twin is signed ONLY when the
    persisted provenance already records one (``has_light_variant``) — no storage probe, unlike the
    per-job view which re-reads provenance from storage. Anonymous callers own no covers, so nothing
    is minted (a READY cover is always owner-scoped)."""
    if owner_id is None:
        return {}
    limit = asyncio.Semaphore(_MAX_CONCURRENT_THUMB_SIGNS)
    course_ids: list[str] = []
    pending: list[Coroutine[Any, Any, CoverThumbs]] = []
    for summary in summaries:
        cover = summary.cover
        if cover is None or cover.status != CoverJobStatus.READY or cover.job_id is None:
            continue
        paths = CoverArtifactPaths.for_coordinates(owner_id, summary.course_id, cover.job_id)
        has_light = cover.provenance is not None and cover.provenance.has_light_variant
        course_ids.append(summary.course_id)
        pending.append(_thumbs_for(storage, paths, has_light=has_light, limit=limit))
    signed = await asyncio.gather(*pending)
    return dict(zip(course_ids, signed, strict=True))


async def _thumbs_for(
    storage: ICoverStorage,
    paths: CoverArtifactPaths,
    *,
    has_light: bool,
    limit: asyncio.Semaphore,
) -> CoverThumbs:
    """Sign one course's cover thumb(s) under the per-request concurrency cap: the dark master's
    derivative always, the light twin only when the cover has one. The two mints are independent, so
    they are gathered."""
    async with limit:
        if has_light:
            thumb, thumb_light = await asyncio.gather(
                mint_cover_thumb(storage, paths.image),
                mint_cover_thumb(storage, paths.image_light),
            )
            return CoverThumbs(thumb_url=thumb, thumb_url_light=thumb_light)
        return CoverThumbs(thumb_url=await mint_cover_thumb(storage, paths.image))
