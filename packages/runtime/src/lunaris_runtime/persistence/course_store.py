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

    def save(self, course: Course) -> Path:
        path = self.path_for(course.id)
        path.write_text(course.model_dump_json(by_alias=True, indent=2))
        return path

    def load(self, course_id: str) -> Course:
        return Course.model_validate_json(self.path_for(course_id).read_text())
