from dataclasses import dataclass

from lunaris_video.models.rendered_scene import RenderedScene
from lunaris_video.schemas.qa_verdict import QaDefect


@dataclass(frozen=True)
class SceneQaResult:
    """One scene's best-effort outcome: the render to ship, plus any imperfection it couldn't clear.

    ``unresolved_defects`` are Gate B's spatial defects; ``sync_issues`` are Gate D / Gate 1
    best-effort messages (a beat that wouldn't sync, or a scene whose render drifts from its audio
    timeline). All are empty when the scene is clean. They are non-empty only when a gate exhausted
    its budget and *degraded to best-effort* — shipping the scene rather than failing or silencing
    the video (the 'publish anyway' policy: every course still carries narration). Both flow into
    provenance, so an imperfect scene is visible in the artifact's record, never presented as clean.
    """

    scene: RenderedScene
    unresolved_defects: tuple[QaDefect, ...] = ()
    sync_issues: tuple[str, ...] = ()
