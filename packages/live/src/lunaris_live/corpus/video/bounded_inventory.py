from collections.abc import Sequence

from .schemas.clip import VideoClip
from .schemas.inventory import VideoGap, VideoInventory


def bounded_inventory(clips: Sequence[VideoClip], gaps: Sequence[VideoGap]) -> VideoInventory:
    """Bound persisted reports while retaining an explicit truncation signal."""
    limited = len(clips) > 5000 or len(gaps) > 1000
    selected = (*gaps[:999], VideoGap(reason="inventory_limit")) if limited else tuple(gaps)
    return VideoInventory(clips=tuple(clips[:5000]), gaps=selected)
