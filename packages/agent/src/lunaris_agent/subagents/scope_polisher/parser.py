"""Tolerant parse of the polish model's reply into reworded delivers/excludes lines.

The model is asked for a JSON object ``{"delivers": [...], "excludes": [...]}`` but may wrap it in
prose or code fences; this extracts the first JSON object and reads two string lists from it,
returning ``None`` on anything unusable so the caller falls back to the deterministic band.
"""

import json
import re

# Greedy (first ``{`` to last ``}``): a multi-object reply fails ``json.loads`` → ``None``, which is
# the correct fall-back to the deterministic band. Matches every sibling parser's convention.
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _string_list(raw: object) -> list[str] | None:
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        return None
    return raw


def parse_polished_lines(raw: str) -> tuple[list[str], list[str]] | None:
    """Return ``(delivers, excludes)`` parsed from the model reply, or ``None`` if unusable."""
    match = _JSON_OBJECT_RE.search(raw)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    delivers = _string_list(payload.get("delivers"))
    excludes = _string_list(payload.get("excludes"))
    if delivers is None or excludes is None:
        return None
    return delivers, excludes
