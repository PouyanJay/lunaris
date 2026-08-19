from fastapi import APIRouter, HTTPException, Response, status
from lunaris_live.session import STUB_SIM_PATH

from .stub_sim_app import STUB_SIM_HTML

router = APIRouter(prefix="/api/live/sims", tags=["live"])

#: Its own router, mounted at its own prefix, because what it serves is not JSON and not a session.
#: A simulator is a *document a frame loads*, and folding it into the session router would put an
#: HTML response on a path everything else answers `application/json` from.

#: What the document is allowed to do, stated in its own headers as well as in the frame's
#: `sandbox` attribute. Belt and braces on purpose: the `sandbox` attribute is the host's claim
#: about the frame and can be dropped by whoever writes the next surface, while this travels with
#: the response no matter who embeds it.
#:
#: `default-src 'none'` with `style-src`/`script-src 'unsafe-inline'` is exactly the shape this
#: document needs — everything it uses is inlined, and nothing external may load. `frame-ancestors`
#: is deliberately *not* narrowed here: the SPA's origin differs per environment and is not known to
#: the API, and the frame's own opaque origin is what actually contains the document.
_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'none'"
)

_STUB_ID = STUB_SIM_PATH.rsplit("/", 1)[-1]


@router.get("/{app_id}", response_class=Response)
async def get_sim_app(app_id: str) -> Response:
    """The document a Tier 3 frame loads (P2b T6).

    One simulator exists and it is a placeholder. A real registry (Phase 3) serves built bundles
    from wherever the factory put them, which is why the socket carries a **URL** rather than a
    bundle: this route is one implementation of "somewhere to load it from", not the shape Phase 3
    is committed to.

    404 for anything else, rather than a friendly empty page. A frame that loaded *something* for an
    unknown id would show a learner a blank simulator and let the turn go on to ask them to
    demonstrate a criterion in it.
    """
    if app_id != _STUB_ID:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such simulator")

    return Response(
        content=STUB_SIM_HTML,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Security-Policy": _CSP,
            # The document is a fixed asset, but it is served from the API's origin, and a browser
            # sniffing it into anything other than HTML is a whole class of problem for one header.
            "X-Content-Type-Options": "nosniff",
            # Fixed per build and safe to keep, which spares a frame re-fetching it on every turn
            # that mounts the same simulator.
            "Cache-Control": "public, max-age=300",
        },
    )
