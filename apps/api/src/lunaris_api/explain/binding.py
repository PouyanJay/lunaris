from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .protocol import IExplainer

# ExplainSource lives beside ExplainBinding (its field's type) as a tightly-coupled sibling —
# the one-export rule's sibling exception, like the draft_throttle error+gate pair.
# Which tier answers an explain call — the wire value the web badge renders. "on-device" exists in
# the same vocabulary but never appears here: that source is decided (and answered) entirely in the
# browser, so the server only ever reports the two tiers it can run itself.
ExplainSource = Literal["hosted", "server-fallback"]


@dataclass(frozen=True)
class ExplainBinding:
    """One request's resolved explain capability: who answers, which tier that is, and the
    credential scope to answer under.

    Resolved per request (never cached) because the explainer's lazy model client would otherwise
    pin the first caller's key — the same BYOK invariant as the build pipeline's per-run factories.
    ``credentials`` is the tenant's own keys to bind around the call (``None`` → process env, the
    auth-off/single-user path).
    """

    explainer: IExplainer
    source: ExplainSource
    credentials: Mapping[str, str] | None
