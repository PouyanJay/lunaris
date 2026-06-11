"""The device build bridge: a keyless Draft build's LLM completions, served by the browser."""

from .bridge import BridgeCompletionRequest, DeviceBridge
from .run_scope import resolve_device_bridge, run_device_bridge

__all__ = [
    "BridgeCompletionRequest",
    "DeviceBridge",
    "resolve_device_bridge",
    "run_device_bridge",
]
