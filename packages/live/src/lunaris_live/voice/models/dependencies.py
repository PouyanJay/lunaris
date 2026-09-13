from dataclasses import dataclass

from ..protocols.audio_store import IVoiceAudioStore
from ..protocols.ledger import IVoiceLedger
from ..protocols.provider import IVoiceProvider
from ..protocols.session_reader import IVoiceSessionReader


@dataclass(frozen=True)
class VoiceDependencies:
    ledger: IVoiceLedger
    audio: IVoiceAudioStore
    provider: IVoiceProvider
    sessions: IVoiceSessionReader
