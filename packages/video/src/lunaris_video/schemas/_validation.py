from lunaris_video.schemas.scene_contract import SceneContract


def assert_unique_scene_ids(scenes: list[SceneContract], context: str) -> None:
    """Reject scene-id collisions — artifacts, logs, QA frames and Scene classes share one
    id-keyed namespace, so a duplicate corrupts every downstream stage."""
    ids = [scene.id for scene in scenes]
    if len(ids) != len(set(ids)):
        raise ValueError(f"scene ids must be unique {context}")
