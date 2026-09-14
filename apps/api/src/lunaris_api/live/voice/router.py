from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from lunaris_live.voice.error import VoiceError
from lunaris_live.voice.models.operation import VoiceOperation
from lunaris_live.voice.protocols.service import IVoiceService
from lunaris_live.voice.schemas.speech_request import SpeechRequest
from lunaris_live.voice.schemas.transcript import VoiceTranscript
from lunaris_runtime.logging import bind_request_id, bind_run_id

from ...dependencies import OptionalUserIdDep
from .dependencies import get_live_voice_service
from .recording_body import read_voice_recording
from .stream_response import VoiceStreamingResponse

router = APIRouter(prefix="/api/live/sessions/{session_id}/voice", tags=["live"])
_Service = Annotated[IVoiceService, Depends(get_live_voice_service)]


@router.post("/transcriptions", response_model=VoiceTranscript)
async def transcribe(
    session_id: str,
    request: Request,
    response: Response,
    service: _Service,
    owner_id: OptionalUserIdDep,
    turn_seq: Annotated[int, Query(alias="turnSeq", ge=1)],
    run_id: Annotated[str, Query(alias="runId", min_length=1, max_length=100)],
    operation_id: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> VoiceTranscript:
    correlation = uuid4().hex
    bind_request_id(correlation)
    bind_run_id(correlation, session_id=session_id)
    headers = {"X-Request-Id": correlation, "X-Session-Id": session_id, "Cache-Control": "no-store"}
    response.headers.update(headers)
    if request.headers.get("content-type", "").split(";")[0] != "audio/wav":
        raise HTTPException(415, "Use a WAV recording.", headers=headers)
    try:
        data = await read_voice_recording(request)
        return await service.transcribe(
            VoiceOperation(
                session_id=session_id,
                owner_id=owner_id,
                operation_id=operation_id,
                run_id=correlation,
                turn_seq=turn_seq,
                source_run_id=run_id,
            ),
            data,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, "Session not found.", headers=headers) from exc
    except VoiceError as exc:
        raise HTTPException(exc.status_code, str(exc), headers=headers) from exc


@router.post("/speech")
async def speech(
    session_id: str, payload: SpeechRequest, service: _Service, owner_id: OptionalUserIdDep
) -> VoiceStreamingResponse:
    correlation = uuid4().hex
    bind_request_id(correlation)
    bind_run_id(correlation, session_id=session_id)
    headers = {"X-Request-Id": correlation, "X-Session-Id": session_id, "Cache-Control": "no-store"}
    try:
        chunks = await service.speech(
            VoiceOperation(
                session_id=session_id,
                owner_id=owner_id,
                operation_id=payload.operation_id,
                run_id=correlation,
                turn_seq=payload.source.turn_seq,
                source_run_id=payload.source.run_id,
                exchange_sequence=payload.source.exchange_sequence,
            )
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, "Session not found.", headers=headers) from exc
    except VoiceError as exc:
        raise HTTPException(exc.status_code, str(exc), headers=headers) from exc
    return VoiceStreamingResponse(
        chunks,
        media_type="audio/pcm",
        headers={
            "X-Request-Id": correlation,
            "X-Session-Id": session_id,
            "X-Audio-Sample-Rate": "24000",
            "Cache-Control": "no-store",
        },
    )
