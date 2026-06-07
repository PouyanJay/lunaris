from pathlib import Path

from lunaris_runtime.schema import Course


class CourseStore:
    """File-backed store for the course-object — the harness virtual FS in MVP.

    Persists each course as ``<id>.json`` (camelCase, the web-facing contract).
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def path_for(self, course_id: str) -> Path:
        return self._root / f"{course_id}.json"

    def save(self, course: Course) -> None:
        # Returns None to satisfy ICourseStore (the Supabase store has no path to return); the file
        # path is available via path_for for file-store-specific callers/tests.
        self.path_for(course.id).write_text(course.model_dump_json(by_alias=True, indent=2))

    def load(self, course_id: str) -> Course:
        return Course.model_validate_json(self.path_for(course_id).read_text())

    def delete(self, course_id: str) -> bool:
        """Delete the stored course file. Idempotent: a missing file is not an error.

        Returns ``True`` if a file was removed, ``False`` if it was already absent — so the caller
        can tell a real deletion from a no-op (e.g. to choose 204 vs 404).
        """
        path = self.path_for(course_id)
        if not path.exists():
            return False
        path.unlink()
        return True
