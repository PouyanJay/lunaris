from typing import Literal

from ....graph.schema.base import LiveModel


class SimAvailability(LiveModel):
    status: Literal[
        "off", "queued", "building", "approved", "rejected", "indeterminate", "unavailable"
    ]
