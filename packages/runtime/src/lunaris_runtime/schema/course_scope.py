from pydantic import Field

from .base import CourseModel


class CourseScope(CourseModel):
    """The scope-realism band (CQ Phase 3.1): an honest, at-a-glance framing of what a course is.

    Computed deterministically at finalize from the brief's abstractions (goal_type, gap
    magnitude, target level, grounding status) — never from a topic — so the reader can show a
    header band that sets expectations: roughly how much effort it takes, and explicitly what it
    does and does not get you. ``None`` on a ``Course`` means the band was not computed (a
    pre-Phase-3 or direct-assembly course), and the reader shows no band.

    The three fields are the *facts*: an optional key-gated polish step may rewrite their wording
    but never their structure (the effort band, the count of delivers/excludes lines) — a promise
    the course cannot keep is never invented downstream of this value.
    """

    # Human-readable effort/timeline band, e.g. "~6-10 weeks, self-paced". Empty = unknown.
    effort: str = ""
    # What the course DOES get you — concrete outcomes, one line each.
    delivers: list[str] = Field(default_factory=list)
    # What it does NOT get you — honest exclusions, one line each.
    excludes: list[str] = Field(default_factory=list)
