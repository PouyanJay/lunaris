"""Wire models for the device build bridge (tightly-coupled siblings of one endpoint pair).

The tab polls completion requests and posts results; both shapes are deliberately minimal —
messages-in, text-out — because the keyless scripted pipeline only ever needs plain completions.
"""

from pydantic import Field

from .base import CamelModel

# A generous bound on one posted completion: far above any real authoring reply (a few thousand
# tokens), small enough that a hostile client can't park megabytes in the run's memory.
MAX_BRIDGE_RESULT_CHARS = 200_000

# Request ids are uuid4().hex (32 chars); the bound leaves headroom while keeping a hostile
# client's posted id from being held as an arbitrarily long dict key.
_REQUEST_ID_MAX = 64


class BridgeMessageView(CamelModel):
    """One message in a parked completion request. Role + content only — the scripted keyless
    pipeline is text-only, so no tool-call fields exist on the wire; extending this means
    revisiting the bridge contract."""

    role: str
    content: str


class BridgeRequestView(CamelModel):
    """One completion the tab must run on its on-device model."""

    request_id: str = Field(max_length=_REQUEST_ID_MAX)
    messages: list[BridgeMessageView]


class BridgeResultRequest(CamelModel):
    """The tab's completed text for one parked request."""

    request_id: str = Field(max_length=_REQUEST_ID_MAX)
    text: str = Field(max_length=MAX_BRIDGE_RESULT_CHARS)
