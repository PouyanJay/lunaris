from dataclasses import dataclass


@dataclass(frozen=True)
class GroundingContext:
    prompt: str
    passages: tuple[tuple[str, str], ...]
    omitted: tuple[str, ...]
    issues: tuple[str, ...]
    source_digest: str
    run_id: str
