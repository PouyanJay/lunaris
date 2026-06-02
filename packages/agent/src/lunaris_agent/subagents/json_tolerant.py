import json

from json_repair import repair_json


def loads_tolerant(raw: str) -> object:
    """Parse model-emitted JSON, repairing the common LLM malformations before giving up.

    The live models occasionally slip a single delimiter inside a large structured response — a
    missing or trailing comma, an unclosed brace — which a strict ``json.loads`` rejects, crashing
    the whole course build over one typo. ``json_repair`` recovers these, so a build survives normal
    model nondeterminism. Truly unsalvageable text (prose, no JSON) re-raises the original
    ``JSONDecodeError`` so the caller's "no usable JSON" path still triggers.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # json_repair yields "" or None when there is nothing to salvage — re-raise the real error.
        repaired = repair_json(raw, return_objects=True)
        if repaired == "" or repaired is None:
            raise
        return repaired
