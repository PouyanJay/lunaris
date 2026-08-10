import json
from typing import Any


def parse_json_object(text: str) -> dict[str, Any] | None:
    """The JSON object in a model response, or ``None``.

    Models wrap JSON in prose and fences however the mood takes them, and a re-ask costs a call and
    seconds a learner is sitting through — so this normalises deterministically rather than
    repairing by prompt.

    It decodes forward from the first brace rather than slicing to the last one: trailing prose can
    easily contain a stray brace, and a fence marker can appear *inside* a string value the model
    wrote. Reading one well-formed object and ignoring whatever follows is both more forgiving and
    incapable of mangling the content it accepts.

    Shared by every adapter in the package. It was written twice before this — once in the compiler
    and once in the grader — with the second copy's docstring saying "same normalisation the
    compiler uses", which is the point at which two copies should have become one.
    """
    start = text.find("{")
    if start == -1:
        return None
    try:
        parsed, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
