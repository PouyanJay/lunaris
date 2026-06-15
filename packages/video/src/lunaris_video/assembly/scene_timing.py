# The on-screen seconds each scene spends fading out AFTER its last beat. The pinned skill ends each
# scene with ``clear_scene(scene, run_time=0.7)`` — a FadeOut of all mobjects for clean concat
# boundaries — rendered after the beat timeline, so a scene's video is this much longer than the sum
# of its beat windows (``total_s``). The audio mix and the caption clock MUST add the same gap after
# each scene, or audio/captions drift this far ahead of the video at every scene boundary, and the
# error compounds across scenes. The deterministic length gate asserts each scene's render lands on
# ``total_s + SCENE_CLOSE_FADE_S`` (within frame quantization), so this is the single source of
# truth for the closing-fade length across mix, captions, and the gate. It MUST track
# ``clear_scene``'s default run_time in the pinned ``assets/style_tokens.py`` (a test pins the two).
SCENE_CLOSE_FADE_S = 0.7
