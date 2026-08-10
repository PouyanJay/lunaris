import hashlib

from lunaris_runtime.schema import CostSubjectType

#: The legacy column's own limit (``check (length(course_id) between 1 and 100)``).
_MAX_LENGTH = 100


def legacy_course_id(subject_type: CostSubjectType, subject_id: str) -> str:
    """The value to write into the cost tables' legacy ``course_id`` column. **Transitional.**

    The column outlives this release by one deploy: CD pushes migrations *before* it rolls the new
    image, so the previous release is still reading and upserting ``course_id`` for the length of a
    changeover, and it is still ``NOT NULL`` with the rollup's primary key on it.

    That primary key is the catch. It constrains a single namespace, so a Live graph whose id
    happened to equal a course's would be rejected — or, worse, silently replace it — which is the
    exact collision the ``(subject_type, subject_id)`` key exists to prevent. Prefixing everything
    that is not a course keeps the legacy column unique across subject types by construction, while
    leaving course rows byte-identical to what the previous release writes and reads.

    A prefixed id that would overrun the column is **hashed rather than truncated**. Truncation
    trades one collision for another: two long ids sharing a prefix would land on the same legacy
    value, and because the primary key is still live that surfaces as a unique violation the
    recorder swallows — a rollup that silently never gets written. Nothing reads a non-course row
    out of this column, so an opaque-but-unique value costs nothing and cannot collide.

    Removed by the contract migration that drops the column.
    """
    if subject_type is CostSubjectType.COURSE:
        # Untouched, byte for byte: these are the rows the previous release still reads.
        return subject_id
    prefixed = f"{subject_type.value}:{subject_id}"
    if len(prefixed) <= _MAX_LENGTH:
        return prefixed
    digest = hashlib.sha256(subject_id.encode()).hexdigest()
    return f"{subject_type.value}:{digest}"[:_MAX_LENGTH]
