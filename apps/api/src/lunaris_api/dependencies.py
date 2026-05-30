from pathlib import Path
from typing import Annotated

from fastapi import Depends
from lunaris_agent import build_orchestrator, build_stub_orchestrator
from lunaris_runtime.persistence import CourseStore

from .config import Settings, get_settings
from .secrets import AnthropicProbeValidator, ISecretValidator, SecretStore
from .service import CourseService


def get_course_service(settings: Annotated[Settings, Depends(get_settings)]) -> CourseService:
    """Compose the CourseService for the configured pipeline (overridable in tests)."""
    store = CourseStore(settings.course_dir)
    factory = build_stub_orchestrator if settings.pipeline == "stub" else build_orchestrator
    return CourseService(store, factory)


CourseServiceDep = Annotated[CourseService, Depends(get_course_service)]

# One SecretStore per secrets-file path (it owns process env + the on-disk file), so all
# requests share the same in-memory + on-disk state. Tests override get_secret_store.
_secret_stores: dict[Path, SecretStore] = {}


def get_secret_store(settings: Annotated[Settings, Depends(get_settings)]) -> SecretStore:
    """The process-wide secret store for the configured secrets path."""
    path = settings.secrets_path
    if path not in _secret_stores:
        _secret_stores[path] = SecretStore(path)
    return _secret_stores[path]


def get_secret_validator() -> ISecretValidator:
    """The live secret validator (probes Anthropic). Tests override with an accepting one."""
    return AnthropicProbeValidator()


SecretStoreDep = Annotated[SecretStore, Depends(get_secret_store)]
SecretValidatorDep = Annotated[ISecretValidator, Depends(get_secret_validator)]
