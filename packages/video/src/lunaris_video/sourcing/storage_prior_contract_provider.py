import structlog
from lunaris_runtime.persistence import IVideoStorage, PersistenceError
from lunaris_runtime.schema import VideoJob, VideoKind
from pydantic import ValidationError

from lunaris_video.schemas import ChapteredSceneContracts, SceneContracts, VideoContract

_logger = structlog.get_logger(__name__)


class StoragePriorContractProvider:
    """Loads a regenerate job's prior contract from the artifact store (``IPriorContractProvider``).

    The regenerate endpoint snapshots the source job's ``scene_contracts.json`` storage path onto
    the new job's ``config["regenerate"]["contract_path"]``; this downloads it and parses it back
    into the contract type the job's kind uses (chaptered for the overview, flat otherwise).
    Best-effort: any miss (no path, the artifact is gone, schema drift) returns ``None`` so the
    pipeline re-plans rather than failing a regenerate.
    """

    def __init__(self, storage: IVideoStorage) -> None:
        self._storage = storage

    async def load(self, job: VideoJob) -> VideoContract | None:
        path = _contract_path(job)
        if path is None:
            return None
        try:
            data = await self._storage.download(path=path)
        except PersistenceError:
            _logger.warning("prior_contract_unavailable", job_id=job.id, path=path)
            return None
        model = ChapteredSceneContracts if job.kind is VideoKind.OVERVIEW else SceneContracts
        try:
            return model.model_validate_json(data)
        except ValidationError:
            _logger.warning("prior_contract_unparseable", job_id=job.id, path=path)
            return None


def _contract_path(job: VideoJob) -> str | None:
    regenerate = job.config.get("regenerate")
    if not isinstance(regenerate, dict):
        return None
    path = regenerate.get("contract_path")
    return path if isinstance(path, str) and path else None
