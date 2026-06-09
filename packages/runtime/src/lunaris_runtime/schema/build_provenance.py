from .base import CourseModel
from .enums import CapabilityMode, CapabilityName


class CapabilityBuildTag(CourseModel):
    """Which provider produced one capability's contribution to a course (keyless-fallbacks T5).

    Captured at finalize from the run's actual credential scope and persisted on the ``Course``, so
    a Draft course carries an honest, permanent record of the fallback that built it — distinct from
    the live capability badge, which reflects the *current* key state and flips the moment a key is
    stored. ``provider`` is the human label of the provider in effect (e.g. ``Anthropic Claude`` or
    ``Qwen2.5-3B (local)``); the tag only changes when the course is rebuilt with a real key.
    """

    capability: CapabilityName
    mode: CapabilityMode
    provider: str
