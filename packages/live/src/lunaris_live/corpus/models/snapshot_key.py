from dataclasses import dataclass


@dataclass(frozen=True)
class SnapshotKey:
    owner_id: str
    course_id: str
    digest: str
    adapter_version: str
    schema_version: str
