from typing import Annotated

from fastapi import Depends
from lunaris_live.corpus.protocols.resolver import ICorpusResolver
from lunaris_live.corpus.stores.supabase_snapshot_store import SupabaseCorpusSnapshotStore
from lunaris_live.corpus.video.protocols.clip_verifier import IVideoClipVerifier
from lunaris_live.corpus.video.protocols.inventory import IVideoInventory

from ...config import Settings, get_settings
from ...dependencies import CourseStoreDep, VideoJobQueueDep, VideoStorageDep
from .access_guard import StudioCorpusAccessGuard
from .media_resolver import CorpusMediaResolver
from .models.media_services import CorpusMediaServices
from .preparer import CorpusGraphPreparer
from .protocols.access_guard import ICorpusAccessGuard
from .protocols.preparer import ICorpusGraphPreparer
from .studio_resolver import StudioCorpusResolver
from .video_inventory import StudioVideoInventory
from .video_media import SignedVideoMedia

_snapshots = SupabaseCorpusSnapshotStore()


def get_corpus_resolver(
    settings: Annotated[Settings, Depends(get_settings)], courses: CourseStoreDep
) -> ICorpusResolver | None:
    return StudioCorpusResolver(courses, _snapshots) if settings.has_supabase else None


def get_corpus_access_guard(courses: CourseStoreDep) -> ICorpusAccessGuard:
    return StudioCorpusAccessGuard(courses)


def get_corpus_inventory(
    courses: CourseStoreDep, queue: VideoJobQueueDep, storage: VideoStorageDep
) -> IVideoInventory:
    return StudioVideoInventory(courses, queue, storage, SignedVideoMedia(storage))


def get_corpus_clip_verifier(
    courses: CourseStoreDep, queue: VideoJobQueueDep, storage: VideoStorageDep
) -> IVideoClipVerifier:
    return StudioVideoInventory(courses, queue, storage, SignedVideoMedia(storage))


def get_corpus_preparer(
    inventory: Annotated[IVideoInventory, Depends(get_corpus_inventory)],
) -> ICorpusGraphPreparer:
    from lunaris_live.corpus.mapping.asset_mapper import AssetMapper

    from ..dependencies import resolve_strong_model

    return CorpusGraphPreparer(AssetMapper(resolve_strong_model()), inventory)


def get_corpus_media_resolver(
    settings: Annotated[Settings, Depends(get_settings)],
    access: Annotated[ICorpusAccessGuard, Depends(get_corpus_access_guard)],
    clip_verifier: Annotated[IVideoClipVerifier, Depends(get_corpus_clip_verifier)],
    storage: VideoStorageDep,
) -> CorpusMediaResolver:
    from ..dependencies import resolve_graph_store
    from ..session.dependencies import _resolve_session_store

    return CorpusMediaResolver(
        CorpusMediaServices(
            _resolve_session_store(settings),
            resolve_graph_store(settings),
            access,
            clip_verifier,
            storage,
        ),
        session_budget_s=settings.live_session_budget_s,
    )
