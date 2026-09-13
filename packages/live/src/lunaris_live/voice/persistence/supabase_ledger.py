from asyncio import to_thread
from typing import Literal
from uuid import UUID

from lunaris_runtime.persistence import supabase_client
from lunaris_runtime.persistence.guard import guard

from ..error import VoiceError
from ..models.operation import VoiceOperation
from .models.admission import VoiceAdmission
from .models.claim import VoiceClaim
from .models.limits import VoiceLimits
from .record_claim import record_claim
from .schemas.result import VoiceResult


class SupabaseVoiceLedger:
    """Single-RPC admission/finalization, shared across API replicas."""

    def __init__(self, *, client: object | None = None, limits: VoiceLimits | None = None) -> None:
        self._client, self._limits = client, limits or VoiceLimits()

    @guard("live voice ledger")
    def _rpc(self, name: str, params: dict[str, object]) -> object:
        if self._client is None:
            self._client = supabase_client(
                url_env="SUPABASE_URL",
                service_key_env="SUPABASE_SERVICE_ROLE_KEY",
                purpose="persist voice operations",
            )
        return self._client.rpc(name, params).execute().data  # type: ignore[attr-defined]

    async def claim(
        self,
        operation: VoiceOperation,
        *,
        kind: Literal["transcription", "speech"],
        fingerprint: str,
        reserve_usd: float,
    ) -> VoiceClaim:
        admission = VoiceAdmission(operation, kind, fingerprint, reserve_usd)
        data = await to_thread(
            self._rpc,
            "claim_live_voice",
            {
                "p_owner": operation.owner_id,
                "p_session": operation.session_id,
                "p_request": self._request_payload(admission),
            },
        )
        return record_claim(operation, _parse_claim(data, operation.session_id))

    def _request_payload(self, admission: VoiceAdmission) -> dict[str, object]:
        return {
            "operation_id": str(admission.operation.operation_id),
            "kind": admission.kind,
            "fingerprint": admission.fingerprint,
            "reserve_usd": admission.reserve_usd,
            "turn_seq": admission.operation.turn_seq,
            "source_run_id": admission.operation.source_run_id,
            "exchange_sequence": admission.operation.exchange_sequence,
            "concurrency": self._limits.concurrency,
            "operations": self._limits.operations,
            "budget_usd": self._limits.reserve_usd,
            "lease_seconds": self._limits.lease_seconds,
            "session_seconds": self._limits.session_seconds,
        }

    async def complete(self, operation: VoiceOperation, token: UUID, result: VoiceResult) -> bool:
        return await self._finish(operation, token, result.model_dump(exclude_none=True))

    async def fail(self, operation: VoiceOperation, token: UUID) -> bool:
        return await self._finish(operation, token, None)

    async def _finish(
        self, operation: VoiceOperation, token: UUID, result: dict[str, object] | None
    ) -> bool:
        return (
            await to_thread(
                self._rpc,
                "finish_live_voice",
                {
                    "p_owner": operation.owner_id,
                    "p_session": operation.session_id,
                    "p_operation": str(operation.operation_id),
                    "p_token": str(token),
                    "p_result": result,
                },
            )
            is True
        )


def _parse_claim(data: object, session_id: str) -> VoiceClaim:
    if not isinstance(data, dict):
        raise VoiceError("Voice storage is unavailable.", status_code=503)
    status = data.get("status")
    if status == "missing":
        raise FileNotFoundError(session_id)
    if status in ("stale", "conflict"):
        raise VoiceError("This voice request is no longer current.")
    if status not in ("started", "completed", "in_progress", "indeterminate", "unavailable"):
        raise VoiceError("Voice storage is unavailable.", status_code=503)
    return VoiceClaim(
        status,
        token=UUID(data["token"]) if data.get("token") else None,
        source_text=data.get("source_text"),
        audio_key=data.get("audio_key"),
        result=VoiceResult.model_validate(data["result"])
        if data.get("result") is not None
        else None,
    )
