from lunaris_video.schemas import VideoContract

# The skill's estimate-mode constants (scripts/narration.py) — kept identical so the timing.json
# this writes is the SAME manifest shape ElevenLabs measured-timing (V3) drops into, zero code
# change downstream. WPM → words/sec; a spoken beat adds a short pause; a beat's on-screen time is
# the longer of its speech and its visual floor.
_WORDS_PER_MINUTE = 150.0
_PAUSE_S = 0.35
_MIN_BEAT_S = 0.6


def estimate_timing(contract: VideoContract) -> dict[str, object]:
    """The WPM-estimated ``timing.json`` for a silent, voice-ready video (skill Stage 2.5).

    Per beat: ``audio_s`` is the spoken length the narration WOULD take (so V3 can compare against
    measured TTS), ``anim_s`` is the actual on-screen time (max of speech and the visual floor),
    ``audio`` is null and ``estimated`` true until real clips replace them. The video renders
    silent now but every duration the narration needs already exists.
    """
    timing: dict[str, object] = {}
    words_per_second = _WORDS_PER_MINUTE / 60.0
    for scene in contract.scenes:
        beats: list[dict[str, object]] = []
        total = 0.0
        for beat in scene.beats:
            words = len(beat.narration.split())
            audio_s = round(words / words_per_second + (_PAUSE_S if words else 0.0), 2)
            floor = beat.min_visual_s if beat.min_visual_s is not None else _MIN_BEAT_S
            anim_s = round(max(audio_s, floor), 2)
            beats.append(
                {
                    "id": beat.id,
                    "audio_s": audio_s,
                    "anim_s": anim_s,
                    "audio": None,
                    "estimated": True,
                }
            )
            total += anim_s
        timing[scene.id] = {"beats": beats, "total_s": round(total, 2)}
    return timing
