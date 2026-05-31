import json
import re

from lunaris_runtime.schema import VisualSpec
from pydantic import TypeAdapter, ValidationError

# Validates a raw dict against the VisualSpec discriminated union (camelCase or snake_case keys, via
# the models' populate_by_name). Built once — TypeAdapter compilation is not free.
_SPEC_ADAPTER: TypeAdapter[VisualSpec] = TypeAdapter(VisualSpec)
# A ```json (or plain ```) fenced object; the language tag is optional for tolerance.
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)
# The first bare {...} object, for responses that emit JSON without a fence.
_BARE_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_visual_spec(text: str) -> VisualSpec | None:
    """Extract a typed VisualSpec from a generator response, or ``None`` for "no spec".

    Tolerant of a ```json fenced block or bare JSON, and of an explicit ``NONE``. Returns ``None``
    (never a half-formed spec) on unparseable JSON, a non-object, an unknown ``type`` discriminator,
    or any field that fails validation — the safety gate the agent can't talk its way past.
    """
    stripped = text.strip()
    if not stripped or stripped.upper().startswith("NONE"):
        return None

    fenced = _JSON_FENCE_RE.search(text)
    bare = _BARE_OBJECT_RE.search(stripped)
    raw = fenced.group(1) if fenced else (bare.group(0) if bare else stripped)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return _SPEC_ADAPTER.validate_python(data)
    except ValidationError:
        return None
