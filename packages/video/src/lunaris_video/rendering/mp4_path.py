from pathlib import Path

# The skill's validated render profile: 720p30 (matches the -qm quality flag the renderer uses).
_QUALITY_DIR = "720p30"


def expected_scene_mp4(scene_file: Path, scene_class_name: str) -> Path:
    """Where manim writes the scene's MP4 for this renderer's profile.

    Used by the renderer to confirm success (a real file, not just exit 0) and by Gate B to
    locate the artifact it inspects — one definition so the two never disagree about the path.
    """
    return (
        scene_file.parent / "media" / "videos" / scene_file.stem / _QUALITY_DIR
    ) / f"{scene_class_name}.mp4"
