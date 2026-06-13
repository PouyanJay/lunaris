from lunaris_video.schemas.chaptered_scene_contracts import ChapteredSceneContracts
from lunaris_video.schemas.scene_contracts import SceneContracts

# Either contract shape — what the hash util and the pipeline's stage boundaries accept.
type VideoContract = SceneContracts | ChapteredSceneContracts
