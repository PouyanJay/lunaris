import asyncio
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from lunaris_runtime.logging import bind_request_id, bind_run_id
from lunaris_runtime.persistence import PersistenceError

from ...dependencies import CurrentUserIdDep
from ..work_refused import LiveWorkRefusedError
from .dependencies import get_corpus_media_resolver
from .media_resolver import CorpusMediaResolver
from .models.media_request import CorpusMediaRequest
from .schemas.media_url import MediaUrl

router = APIRouter(prefix="/api/live/sessions", tags=["live"])


@router.get("/{session_id}/materials/{asset_id}/media", response_model=MediaUrl)
async def material_media(
    session_id: str,
    asset_id: str,
    response: Response,
    owner_id: CurrentUserIdDep,
    service: Annotated[CorpusMediaResolver, Depends(get_corpus_media_resolver)],
    turn: Annotated[int, Query(ge=1)],
) -> MediaUrl:
    run_id = uuid4().hex
    bind_request_id(run_id)
    bind_run_id(run_id, session_id=session_id)
    headers = {"Cache-Control": "no-store", "X-Request-Id": run_id, "X-Session-Id": session_id}
    response.headers.update(headers)
    try:
        async with asyncio.timeout(45):
            return await service.resolve(
                CorpusMediaRequest(
                    session_id=session_id,
                    asset_id=asset_id,
                    turn=turn,
                    owner_id=owner_id,
                    run_id=run_id,
                )
            )
    except TimeoutError as exc:
        raise HTTPException(
            504, "Material verification timed out. Try again.", headers=headers
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, "Session not found.", headers=headers) from exc
    except LiveWorkRefusedError as exc:
        raise HTTPException(exc.status_code, exc.detail, headers=headers) from exc
    except PersistenceError as exc:
        raise HTTPException(
            503, "Material storage is unavailable. Try again.", headers=headers
        ) from exc
