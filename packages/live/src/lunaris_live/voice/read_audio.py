import io
import wave

from .error import VoiceError
from .models.recorded_audio import RecordedAudio


def read_audio(data: bytes) -> RecordedAudio:
    """Validate the browser's bounded PCM WAV before any paid transcription."""
    if len(data) > 1920044:
        raise VoiceError("Recording exceeds the 60-second limit.", status_code=413)
    try:
        with wave.open(io.BytesIO(data), "rb") as source:
            if (
                source.getnchannels(),
                source.getsampwidth(),
                source.getframerate(),
                source.getcomptype(),
            ) != (1, 2, 16000, "NONE"):
                raise ValueError("Unsupported recording")
            frames = source.getnframes()
            if not 1 <= frames <= 960000 or len(source.readframes(frames)) != frames * 2:
                raise ValueError("Incomplete recording")
    except (wave.Error, EOFError, ValueError, RuntimeError) as exc:
        raise VoiceError("Use a mono 16kHz PCM16 WAV recording.", status_code=422) from exc
    return RecordedAudio(data=data, duration_s=frames / 16000)
