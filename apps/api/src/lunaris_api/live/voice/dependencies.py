from fastapi import HTTPException
from lunaris_live.voice.service import VoiceService


def get_live_voice_service() -> VoiceService:
    """Remain unavailable until production admission and provider composition are installed."""
    raise HTTPException(503, "Voice is unavailable. Continue with text.")
