"""Shared GENERAL-preset test doubles (kept out of pytest collection by the leading underscore).

The stubs dispatch on ``FIELDS_MARKER`` — the field name the production ``_GENERAL_FIELDS_TEMPLATE``
asks for in its inline JSON example. If that field is ever renamed in
``cover_art_director.py``, update the marker here; both test files import from this one module so
the drift is a single visible break, not two silent ones.
"""

FIELDS_MARKER = '"title_lines"'

FIELDS_JSON = (
    '{"subject": "How the system works end to end", '
    '"primary_visual": "a refined 3D hero mechanism", '
    '"supporting_visuals": "connected components and flowing paths", '
    '"process_visualization": "a clear left-to-right flow", '
    '"eyebrow": "PROFESSIONAL EDUCATION COURSE", '
    '"title_lines": ["How", "HTTPS", "works"], '
    '"highlight_line": "HTTPS", '
    '"subtitle": "A guided tour", '
    '"badges": ["FOUNDATIONAL", "PRACTICAL", "ESSENTIAL"], '
    '"callouts": ["TLS", "TCP"], '
    '"accuracy_requirements": ["show the handshake before the data flow"]}'
)

# A second, distinguishable field set — the revision-round tests assert the retry re-assembled the
# template with NEW fields, not the first attempt's.
FIELDS_JSON_REVISED = (
    '{"subject": "How the system works end to end", '
    '"primary_visual": "a calmer matte-ceramic hero mechanism", '
    '"supporting_visuals": "fewer, quieter supporting elements", '
    '"process_visualization": "a clear left-to-right flow", '
    '"eyebrow": "PROFESSIONAL EDUCATION COURSE", '
    '"title_lines": ["How", "HTTPS", "works"], '
    '"highlight_line": "HTTPS", '
    '"subtitle": "A guided tour", '
    '"badges": ["FOUNDATIONAL", "PRACTICAL", "ESSENTIAL"], '
    '"callouts": []}'
)


def is_fields_ask(prompt: str) -> bool:
    """Whether ``prompt`` is the GENERAL structured-fields ask (vs the editorial prose ask)."""
    return FIELDS_MARKER in prompt
