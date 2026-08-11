"""Lunaris Live's AG-UI transport — the session as a stream of events.

The wire CopilotKit is written against, spoken here by ``ag-ui-protocol``. Translation lives on this
side of the boundary on purpose: ``lunaris_live.session`` stays transport-agnostic, because AG-UI is
a wire format rather than a fact about teaching, and a second surface (voice, Phase 4) must not have
to unpick an event schema to reuse the loop.

Only ``router`` is re-exported, and that is deliberate. A name re-exported here *shadows* the
submodule it came from — ``agui.session_events`` would resolve to the function rather than the
module — which quietly breaks anything addressing the module by path, ``monkeypatch.setattr``
included. One shadow is the price of mounting the router; a second earns nothing.
"""

from .router import router

__all__ = ["router"]
