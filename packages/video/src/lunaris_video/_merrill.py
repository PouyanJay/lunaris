"""Merrill segment order — a domain invariant shared by the sourcing and grounding modules.

Both the prose flattener and the grounding-packet builder walk a lesson's four phases in teaching
order; keeping the order in one place stops the two from silently diverging.
"""

SEGMENT_ORDER: tuple[str, ...] = ("activate", "demonstrate", "apply", "integrate")
