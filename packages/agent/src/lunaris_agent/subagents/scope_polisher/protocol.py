from typing import Protocol

from lunaris_runtime.schema import CourseBrief, CourseScope


class IScopePolisher(Protocol):
    """Refines the *wording* of a scope-realism band without changing its facts (CQ Phase 3.1).

    The deterministic estimator owns the facts: the effort band, and the count and meaning of the
    delivers/excludes lines. This collaborator may only rewrite those lines into crisper, warmer
    copy — it must never change the effort, alter the line count, or invent a promise. The contract
    is enforced in code (``reconcile_scope``), not on trust, so a misbehaving model degrades to the
    deterministic band. Swappable like every subagent: a live Claude polisher vs. a stub identity
    (the no-key path), and best-effort — any failure returns the band unchanged.
    """

    async def polish(self, scope: CourseScope, *, brief: CourseBrief | None) -> CourseScope: ...
