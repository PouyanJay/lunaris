from .base import CamelModel


class CapabilityStatusView(CamelModel):
    """One capability's active provider on the wire: live (keyed) or its keyless fallback.

    ``compute`` is ``"gpu"``/``"cpu"`` for a keyless fallback that runs on the local model server
    (the LLM), else ``None`` — so the Draft UI can show whether inference is on GPU or CPU.
    """

    capability: str
    mode: str
    provider: str
    compute: str | None = None
