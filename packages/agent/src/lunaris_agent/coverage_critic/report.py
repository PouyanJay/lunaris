"""The coverage critic's verdict (CQ Phase 4.2).

Transient working state read by ``finalize_course`` to gate the build — never on the wire (the
*outcome* surfaces to the learner as an honest scope cut + a review flag, not as this report). So it
is a frozen dataclass (a domain value flowing inside Python), not a Pydantic contract.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CoverageGap:
    """One promised competency the course does not materially build.

    ``competency`` is the researched competency (verbatim from ``StandardResearch``) that the course
    promised but left unbuilt; ``reason`` is why it was ruled unbuilt — the LLM judge's verdict, or
    the deterministic fail-safe's "no module is tagged with it".
    """

    competency: str
    reason: str


@dataclass(frozen=True)
class CoverageReport:
    """Which promised competencies the course materially builds — empty ``gaps`` == every one built.

    A non-empty ``gaps`` is folded into the course's honest scope (excludes + scope_note) AND flags
    the course for review (owner Q3): "promised but not built" becomes an honest scope cut, never a
    silent omission. A clean report (the all-built happy path) leaves the course untouched.
    """

    gaps: list[CoverageGap] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.gaps
