from typing import Protocol

from ..models.verification_request import ClipVerificationRequest


class IVideoClipVerifier(Protocol):
    async def verify(self, request: ClipVerificationRequest) -> bool:
        """Revalidate one exact current owned clip without enumerating unrelated media."""
        ...
