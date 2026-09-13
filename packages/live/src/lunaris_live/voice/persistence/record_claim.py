import structlog

from ..models.operation import VoiceOperation
from .models.claim import VoiceClaim


def record_claim(operation: VoiceOperation, claim: VoiceClaim) -> VoiceClaim:
    structlog.get_logger().info(
        "live.voice.admission",
        session_id=operation.session_id,
        run_id=operation.run_id,
        operation_id=str(operation.operation_id),
        status=claim.status,
    )
    return claim
