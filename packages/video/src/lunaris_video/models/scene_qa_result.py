from dataclasses import dataclass

from lunaris_video.models.rendered_scene import RenderedScene
from lunaris_video.schemas.qa_verdict import QaDefect


@dataclass(frozen=True)
class SceneQaResult:
    """Gate B's outcome for one scene: the render to ship, and any defect it could not clear.

    ``unresolved_defects`` is empty when the scene passed visual QA cleanly. It is non-empty only
    when the repair budget was exhausted (or a visual repair broke the render) and the gate
    *degraded to best-effort* — keeping the least-defective renderable scene and shipping the video
    rather than failing the whole video on one stubborn scene (the 'publish anyway' policy). The
    recorded defects flow into the video's provenance, so a degraded scene is visible in the
    artifact's record, never silently presented as clean.
    """

    scene: RenderedScene
    unresolved_defects: tuple[QaDefect, ...] = ()
