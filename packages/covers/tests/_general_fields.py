"""Shared GENERAL-preset test doubles (kept out of pytest collection by the leading underscore).

The stubs dispatch on ``FIELDS_MARKER`` — the field name the production ``_GENERAL_FIELDS_TEMPLATE``
asks for in its inline JSON example. If that field is ever renamed in
``cover_art_director.py``, update the marker here; both test files import from this one module so
the drift is a single visible break, not two silent ones.
"""

FIELDS_MARKER = '"primary_visual"'

FIELDS_JSON = (
    '{"subtitle": "A guided tour", "subject": "How the system works end to end", '
    '"primary_visual": "a refined 3D hero mechanism", '
    '"supporting_visuals": "connected components and flowing paths", '
    '"process_visualization": "a clear left-to-right flow"}'
)

# A second, distinguishable field set — the revision-round tests assert the retry re-assembled the
# template with NEW fields, not the first attempt's.
FIELDS_JSON_REVISED = (
    '{"subtitle": "A guided tour", "subject": "How the system works end to end", '
    '"primary_visual": "a calmer matte-ceramic hero mechanism", '
    '"supporting_visuals": "fewer, quieter supporting elements", '
    '"process_visualization": "a clear left-to-right flow"}'
)


def is_fields_ask(prompt: str) -> bool:
    """Whether ``prompt`` is the GENERAL structured-fields ask (vs the editorial prose ask)."""
    return FIELDS_MARKER in prompt
