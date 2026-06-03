import re

import structlog

from ..json_tolerant import loads_tolerant
from .profile import LearnerProfile

logger = structlog.get_logger()

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_profile(text: str) -> LearnerProfile:
    """Parse the profiler's JSON into a ``LearnerProfile``.

    Tolerant of prose/code-fences. An absent or malformed frontier degrades to empty (treat as a
    novice — teach from the foundations) rather than crashing the build; the degradation is logged.
    """
    match = _JSON_OBJECT_RE.search(text)
    data = loads_tolerant(match.group(0)) if match else None
    if not isinstance(data, dict):
        logger.warning("learner_profile_unparseable", reason="no JSON object in response")
        return LearnerProfile(frontier=[])
    raw = data.get("frontier", [])
    if not isinstance(raw, list):
        logger.warning("learner_profile_invalid_frontier_type", got=type(raw).__name__)
        return LearnerProfile(frontier=[])
    frontier = [descriptor for item in raw if (descriptor := str(item).strip())]
    return LearnerProfile(frontier=frontier)
