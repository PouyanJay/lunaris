import hashlib
import importlib.util
import os
import tempfile
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Annotated, get_type_hints

import structlog
from fastapi import Depends, Header, HTTPException, status
from lunaris_agent import (
    LessonRegenerator,
    build_agent_course_builder,
    build_orchestrator,
    build_stub_orchestrator,
)
from lunaris_agent.subagents.goal_interpreter import (
    ClaudeGoalInterpreter,
    DefaultGoalInterpreter,
    IGoalInterpreter,
)
from lunaris_grounding import (
    InMemoryCorpusStore,
    InMemorySourceAuthorityStore,
    ISourceAuthorityStore,
    StubEmbedder,
    SupabaseCorpusStore,
    SupabaseSourceAuthorityStore,
    VoyageEmbedder,
)
from lunaris_runtime.device_bridge import BridgeLimits
from lunaris_runtime.persistence import (
    CourseStore,
    ICourseStore,
    InMemoryRunEventStore,
    InMemoryRunStore,
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
    IRunEventStore,
    IRunStore,
    IVideoJobQueue,
    IVideoStorage,
    SupabaseCourseStore,
    SupabaseRunEventStore,
    SupabaseRunStore,
    SupabaseVideoJobQueue,
    SupabaseVideoStorage,
)
from lunaris_runtime.video_build import (
    IVideoBuildCoordinator,
    QueueVideoBuildCoordinator,
    VideoConfig,
)
from lunaris_video import (
    IVideoPipeline,
    StubVideoPipeline,
    build_video_pipeline,
)
from structlog.contextvars import bind_contextvars

from .activity import (
    IActivityStore,
    InMemoryActivityStore,
    LearningEventEmitter,
    SupabaseActivityStore,
)
from .admin_users import (
    InMemoryUserDirectory,
    IUserDirectory,
    SupabaseUserDirectory,
)
from .auth import (
    AuthError,
    CompositeUserVerifier,
    IUserVerifier,
    JwksUserVerifier,
    JwtUserVerifier,
    UserClaims,
)
from .bookmarks import IBookmarkStore, InMemoryBookmarkStore, SupabaseBookmarkStore
from .config import Settings, get_settings
from .config_store import ConfigStore
from .corpus_service import CorpusService
from .credential_vault import CredentialVault
from .device_bridge_registry import DeviceBridgeRegistry
from .draft_throttle import KeylessBuildThrottle
from .explain import ClaudeExplainer, ExplainBinding
from .explain_throttle import KeylessExplainThrottle
from .prod_ops import FakeProdOpsProvider, IProdOpsProvider
from .progress import InMemoryProgressStore, IProgressStore, SupabaseProgressStore
from .run_registry import RunRegistry
from .secrets import (
    BYOK_PROVIDERS,
    KNOWN_SECRETS,
    AnthropicProbeValidator,
    CompositeSecretValidator,
    ElevenLabsProbeValidator,
    ICredentialStore,
    InMemoryCredentialStore,
    ISecretValidator,
    SecretCipher,
    SecretStore,
    SupabaseCredentialStore,
    build_secret_cipher,
)
from .service import (
    ConfigResolver,
    CourseService,
    CredentialResolver,
    PipelineFactory,
    VideoCoordinatorFactory,
)
from .signup_gate import (
    InMemorySignupGateStore,
    ISignupGateStore,
    SignupGateService,
    SupabaseSignupGateStore,
)
from .user_config import (
    InMemoryUserConfigStore,
    IUserConfigStore,
    SupabaseUserConfigStore,
    UserConfigService,
    to_env_map,
)

logger = structlog.get_logger()

# Worker-tier model for the cheap, short calls (Explain + the P7.5 brief interpretation behind the
# clarifier); overridable via the usual env knob. One literal so a model bump is a single edit.
_WORKER_MODEL = "claude-haiku-4-5-20251001"

# LUNARIS_PIPELINE → the per-run pipeline factory. ``agent`` (the default) is the real deep-agent
# harness; ``stub`` is the deterministic no-key demo; ``live`` is the legacy orchestrator.
_PIPELINE_FACTORIES: dict[str, PipelineFactory] = {
    "stub": build_stub_orchestrator,
    "agent": build_agent_course_builder,
    "live": build_orchestrator,
}


def pipeline_supports_lesson_regeneration(pipeline: str) -> bool:
    """Whether the configured pipeline implements the optional ``LessonRegenerator`` capability.

    Derived from the factory's declared return type — never by instantiating it (building the agent
    pipeline constructs LLM clients and needs an API key) — so it stays in lockstep with the
    ``isinstance(pipeline, LessonRegenerator)`` gate in ``CourseService.regenerate_lesson``: the
    single-shot Orchestrator regenerates, the deep-agent builder does not. The web reads this to
    show or hide the per-lesson regenerate action instead of offering a button that always 501s.
    (``issubclass`` against the runtime_checkable Protocol matches method *names* only — sufficient
    for the closed, hand-curated set of pipeline factories.)
    """
    factory = _PIPELINE_FACTORIES.get(pipeline)
    if factory is None:
        return False
    try:
        return_type = get_type_hints(factory).get("return")
    except Exception:
        # A factory whose annotations can't be resolved (e.g. PEP 563 string hints losing a name in
        # scope) falls back to "unsupported" — the same fail-safe as an unknown pipeline above.
        return False
    return isinstance(return_type, type) and issubclass(return_type, LessonRegenerator)


# One run store per process, shared across requests (mirrors _secret_stores). The in-memory
# fallback MUST be a singleton or the sidebar would see an empty history every request; the
# Supabase store is shared too, so its lazy client is built once, not per request. Tests inject
# their own via the get_course_service override.
_in_memory_run_store = InMemoryRunStore()
_supabase_run_store = SupabaseRunStore()

# The replayable build-event log (build-timeline Phase B), one per process (same singleton rationale
# as the run store: an in-memory log must be shared so a build's writes survive for a later replay
# read). The Supabase-store singleton rationale lives in get_run_event_store's docstring.
_in_memory_run_event_store = InMemoryRunEventStore()
_supabase_run_event_store = SupabaseRunEventStore()

# The durable course store (one per process, same lazy-client rationale as the run store): its
# service-role client is built on first write, so the singleton needs no network until then. The
# file-backed store is built per-request from course_dir (cheap), so it isn't a singleton.
_supabase_course_store = SupabaseCourseStore()

# One in-flight run-task registry per process, shared across requests — the cancel request and the
# build request must see the same in-flight set, so this MUST be a singleton.
_run_registry = RunRegistry()


def get_run_registry() -> RunRegistry:
    """The process-wide registry of in-flight build tasks (for cancellation)."""
    return _run_registry


# Process-wide singleton: the build request and the tab's bridge polls arrive on separate HTTP
# connections (separate DI scopes), so the registry must live above both — RunRegistry's twin.
_device_bridge_registry = DeviceBridgeRegistry()


def get_device_bridge_registry() -> DeviceBridgeRegistry:
    """The process-wide registry of in-flight device bridges (device-compute Draft builds)."""
    return _device_bridge_registry


DeviceBridgeRegistryDep = Annotated[DeviceBridgeRegistry, Depends(get_device_bridge_registry)]


def get_run_store(settings: Annotated[Settings, Depends(get_settings)]) -> IRunStore:
    """The run-history index: Supabase when creds are present, else the in-process fallback.

    The Supabase client is lazy, so the process-wide instance needs no network until the first
    write touches the environment. Without creds, history lives for the process lifetime only
    (durable, cross-machine history requires Supabase).
    """
    if settings.has_supabase:
        return _supabase_run_store
    return _in_memory_run_store


def get_run_event_store(settings: Annotated[Settings, Depends(get_settings)]) -> IRunEventStore:
    """The replayable build-event log: Supabase when creds are present, else the in-process store.

    Same lazy-client / process-singleton posture as ``get_run_store`` — without creds the log lives
    for the process lifetime only (durable, cross-machine replay requires Supabase).
    """
    if settings.has_supabase:
        return _supabase_run_event_store
    return _in_memory_run_event_store


# The video-job queue + artifact storage (explainer-video V0), one per process — same singleton /
# lazy-client posture as the run stores. The in-memory pair serves tests and Supabase-less dev;
# the lifespan worker and the request DI must see the SAME instances or enqueues would vanish.
_in_memory_video_queue = InMemoryVideoJobQueue()
_supabase_video_queue = SupabaseVideoJobQueue()
_in_memory_video_storage = InMemoryVideoStorage()
_supabase_video_storage = SupabaseVideoStorage()


def get_video_job_queue(settings: Annotated[Settings, Depends(get_settings)]) -> IVideoJobQueue:
    """The video-job queue: Supabase (durable, SKIP LOCKED claims) when keyed, else in-memory."""
    if settings.has_supabase:
        return _supabase_video_queue
    return _in_memory_video_queue


def get_video_storage(settings: Annotated[Settings, Depends(get_settings)]) -> IVideoStorage:
    """The video-artifact store: the private course-videos bucket when keyed, else in-memory."""
    if settings.has_supabase:
        return _supabase_video_storage
    return _in_memory_video_storage


VideoJobQueueDep = Annotated[IVideoJobQueue, Depends(get_video_job_queue)]
VideoStorageDep = Annotated[IVideoStorage, Depends(get_video_storage)]


def _video_coordinator_factory(
    queue: IVideoJobQueue, storage: IVideoStorage
) -> VideoCoordinatorFactory:
    """Build a per-run video-build coordinator over the shared queue + storage (explainer-video V4).

    Returned to ``CourseService`` only when ``VIDEO_GENERATION_ENABLED`` is on (so its presence is
    the operator gate); the service calls it per keyed, owned build (with the owner's resolved video
    config) to enqueue that build's videos — at the tenant's chosen lengths + voice (V6) — onto the
    same queue the lifespan worker drains, and (at finalize) to await them and read the finished
    artifacts from the same storage the worker wrote them to."""

    def build(owner_id: str, video_config: VideoConfig) -> IVideoBuildCoordinator:
        return QueueVideoBuildCoordinator(
            queue=queue, storage=storage, owner_id=owner_id, video_config=video_config
        )

    return build


def _resolve_course_store(settings: Settings) -> ICourseStore:
    """The finished-course store for the environment — Supabase (durable) or file (offline dev)."""
    return _supabase_course_store if settings.has_supabase else CourseStore(settings.course_dir)


def get_course_store(settings: Annotated[Settings, Depends(get_settings)]) -> ICourseStore:
    """The finished-course store as a request dependency — used by the on-demand video enqueue
    endpoint to verify the caller owns the course (and the lesson exists) before enqueuing."""
    return _resolve_course_store(settings)


CourseStoreDep = Annotated[ICourseStore, Depends(get_course_store)]


def get_video_pipeline(settings: Settings) -> IVideoPipeline:
    """The worker's video pipeline: the real Manim pipeline where the render toolchain is present,
    else the stub.

    V1 swap point — keyed renders run the real plan→code→render→QA→assemble pipeline (lessons
    loaded from the course store). Where the render extra is absent (CI, a lean image), the stub
    keeps the job spine working rather than crash-looping the worker on a missing import. Prod is
    dark until V7 regardless (the worker only starts when ``VIDEO_GENERATION_ENABLED``).
    """
    if importlib.util.find_spec("manim") is None:
        logger.info("video_pipeline_stub", reason="render extra not installed")
        return StubVideoPipeline()
    # Owner-only render workspace; per-job subdirs are uuid4-named (unguessable). A unique
    # mkdtemp root + per-job disk quota is the V7 container's hardening (S1).
    workspace_root = Path(tempfile.gettempdir()) / "lunaris-video-workspace"
    workspace_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    workspace_root.chmod(0o700)  # mkdir(exist_ok) skips mode on a pre-existing dir; enforce it
    # The kind-routing pipeline (V5): one worker pipeline that routes lesson / summary / overview
    # jobs to their configured inner pipelines (the overview chaptered). Storage is wired so a
    # regenerate (V6-T2) can reuse the prior job's contract from the artifact store.
    return build_video_pipeline(
        store=_resolve_course_store(settings),
        workspace_root=workspace_root,
        storage=get_video_storage(settings),
    )


# Process-wide corpus collaborators (singletons, like the run store): the in-memory corpus must be
# shared so a manually-ingested source survives for a later list/delete within the process; the
# Supabase store + Voyage embedder are shared so their lazy clients are built once, not per request.
# The in-memory store is the no-key fallback (lost on restart). Tests inject their own via override.
_in_memory_corpus_store = InMemoryCorpusStore()
_supabase_corpus_store = SupabaseCorpusStore()
_voyage_embedder = VoyageEmbedder()


def get_corpus_service(settings: Annotated[Settings, Depends(get_settings)]) -> CorpusService:
    """The manual-ingest service: real Voyage embeddings + Supabase corpus when keyed, else the
    in-memory store + a deterministic stub embedder (so manual ingest runs offline, non-durably)."""
    if settings.has_supabase and settings.has_embeddings:
        return CorpusService(_supabase_corpus_store, _voyage_embedder)
    logger.info("corpus_service_in_memory", reason="supabase/embeddings creds unset")
    return CorpusService(_in_memory_corpus_store, StubEmbedder())


CorpusServiceDep = Annotated[CorpusService, Depends(get_corpus_service)]

# The editable trust config (P6.2), one per process (same singleton rationale as the corpus store):
# an in-memory config must be shared so an added authority survives for a later list/delete within
# the process; the Supabase store is shared so its lazy client is built once. The in-memory store is
# the no-key fallback (empty + lost on restart — the durable, seeded config requires Supabase).
_in_memory_authority_store = InMemorySourceAuthorityStore()
_supabase_authority_store = SupabaseSourceAuthorityStore()


def get_authority_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ISourceAuthorityStore:
    """The trust-config store: Supabase (the seeded, durable table) when keyed, else in-memory."""
    if settings.has_supabase:
        return _supabase_authority_store
    return _in_memory_authority_store


AuthorityStoreDep = Annotated[ISourceAuthorityStore, Depends(get_authority_store)]

# One SecretStore per .env path (it owns process env + the on-disk file), so all requests share
# the same on-disk state. Tests override get_secret_store.
_secret_stores: dict[Path, SecretStore] = {}


def get_secret_store(settings: Annotated[Settings, Depends(get_settings)]) -> SecretStore:
    """The process-wide secret store for the configured .env path."""
    path = settings.env_file
    if path not in _secret_stores:
        _secret_stores[path] = SecretStore(path)
    return _secret_stores[path]


def get_secret_validator() -> ISecretValidator:
    """The live secret validator (probes Anthropic + ElevenLabs). Tests override with an accepting
    one. Each probe no-ops for a name that is not its own, so composing them covers every keyed
    provider with one validator."""
    return CompositeSecretValidator([AnthropicProbeValidator(), ElevenLabsProbeValidator()])


SecretStoreDep = Annotated[SecretStore, Depends(get_secret_store)]
SecretValidatorDep = Annotated[ISecretValidator, Depends(get_secret_validator)]

# Process-wide BYOK credential stores (singletons, like the run/corpus stores): the in-memory store
# must be shared so a key set in one request survives for the next within the process; the Supabase
# store is shared so its lazy service-role client is built once. The in-memory store is the no-key
# fallback (lost on restart). Tests inject their own via the get_credential_store override.
_in_memory_credential_store = InMemoryCredentialStore()
_supabase_credential_store = SupabaseCredentialStore()


def get_credential_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ICredentialStore:
    """The BYOK credential store: Supabase (durable, RLS server-only) when keyed, else in-memory."""
    if settings.has_supabase:
        return _supabase_credential_store
    return _in_memory_credential_store


# Cipher cache keyed on a SHA-256 digest of the master key — NOT the key itself, so the raw base64
# secret is never retained as a cache key (an lru_cache would keep it in its wrapper dict). The
# AES-GCM context is built once per key and reused across requests.
_cipher_by_key_digest: dict[bytes, SecretCipher] = {}


def _build_cipher(master_key_b64: str | None) -> SecretCipher | None:
    """The at-rest cipher for the configured master key, or ``None`` when BYOK is off. A
    present-but-malformed key raises ``MasterKeyUnavailableError`` (a loud deployment error)."""
    if not master_key_b64:
        return None
    digest = hashlib.sha256(master_key_b64.encode()).digest()
    if digest not in _cipher_by_key_digest:
        cipher = build_secret_cipher(master_key_b64)
        assert cipher is not None  # non-empty key → build_secret_cipher returns a cipher or raises
        _cipher_by_key_digest[digest] = cipher
    return _cipher_by_key_digest[digest]


def get_credential_vault(
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[ICredentialStore, Depends(get_credential_store)],
    validator: SecretValidatorDep,
) -> CredentialVault | None:
    """The BYOK vault, or ``None`` when BYOK is unconfigured (no master key) → the route 503s. The
    cipher is the gate: present ⇒ BYOK is on; the store + validator compose with it."""
    cipher = _build_cipher(settings.key_enc_master)
    if cipher is None:
        return None
    return CredentialVault(store=store, cipher=cipher, validator=validator)


CredentialVaultDep = Annotated[CredentialVault | None, Depends(get_credential_vault)]

# Process-wide per-user config stores (singletons, like the credential/run stores): the in-memory
# store must be shared so a value set in one request survives the next within the process; the
# Supabase store is shared so its lazy service-role client is built once. In-memory is the no-DB
# fallback (auth-on hermetic tests / dev without Supabase).
_in_memory_user_config_store = InMemoryUserConfigStore()
_supabase_user_config_store = SupabaseUserConfigStore()


def get_user_config_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> IUserConfigStore:
    """The per-user config store: Supabase (durable, owner-scoped RLS) when keyed, else memory."""
    if settings.has_supabase:
        return _supabase_user_config_store
    return _in_memory_user_config_store


UserConfigStoreDep = Annotated[IUserConfigStore, Depends(get_user_config_store)]


def get_user_config_service(store: UserConfigStoreDep) -> UserConfigService:
    """The per-user runtime-config surface (model selection) for ``/api/config`` when auth is on."""
    return UserConfigService(store)


UserConfigServiceDep = Annotated[UserConfigService, Depends(get_user_config_service)]

# The signup invite-gate stores (process-wide singletons, like the per-user config stores): the
# Supabase store is shared so its lazy service-role client is built once; the in-memory store holds
# the single gate value for the no-DB/dev path. The auth hook enforces the gate at signup; these
# back the admin screen (read/rotate/toggle) and the public "is a code required?" status.
_in_memory_signup_gate_store = InMemorySignupGateStore()
_supabase_signup_gate_store = SupabaseSignupGateStore()


def get_signup_gate_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ISignupGateStore:
    """The signup-gate store: Supabase (durable, service-role) when keyed, else in-memory."""
    if settings.has_supabase:
        return _supabase_signup_gate_store
    return _in_memory_signup_gate_store


SignupGateStoreDep = Annotated[ISignupGateStore, Depends(get_signup_gate_store)]


def get_signup_gate_service(store: SignupGateStoreDep) -> SignupGateService:
    """The signup-gate surface behind the admin screen and the public status endpoint."""
    return SignupGateService(store)


SignupGateServiceDep = Annotated[SignupGateService, Depends(get_signup_gate_service)]

# The admin user directory (list/delete Supabase Auth accounts). Supabase service-role in
# production; the in-memory fake is the no-DB/test path. Process-wide singletons like the other
# Supabase clients so the lazy service-role client is built once.
_in_memory_user_directory = InMemoryUserDirectory()
_supabase_user_directory = SupabaseUserDirectory()


def get_user_directory(
    settings: Annotated[Settings, Depends(get_settings)],
) -> IUserDirectory:
    """The admin user directory: Supabase Auth admin API when keyed, else the in-memory fake."""
    if settings.has_supabase:
        return _supabase_user_directory
    return _in_memory_user_directory


UserDirectoryDep = Annotated[IUserDirectory, Depends(get_user_directory)]

# The prod-operations provider behind the admin dashboard (cost/compute/power over rg-lunaris-prod).
# Process-wide singleton like the other admin providers. The in-memory fake is the no-Azure/test
# path; the real ARM adapter (authed via the API's managed identity) is selected in cloud.
_fake_prod_ops_provider = FakeProdOpsProvider()

# Default set of prod apps the on/off switch governs (the API + the scale-to-zero workers).
_DEFAULT_GOVERNED_APPS = (
    "lunaris-prod-api",
    "lunaris-prod-video-worker",
    "lunaris-prod-inference",
    "lunaris-prod-embeddings",
)


@lru_cache
def _build_prod_ops_provider() -> IProdOpsProvider:
    """Select the prod-operations provider once. The Azure ARM adapter when the subscription and
    the ACA-injected managed-identity env are present; else the in-memory fake (local/dev/tests)."""
    subscription_id = os.environ.get("PROD_OPS_SUBSCRIPTION_ID")
    identity_endpoint = os.environ.get("IDENTITY_ENDPOINT")
    identity_header = os.environ.get("IDENTITY_HEADER")
    client_id = os.environ.get("PROD_OPS_MI_CLIENT_ID") or os.environ.get("AZURE_CLIENT_ID")
    if not (subscription_id and identity_endpoint and identity_header and client_id):
        return _fake_prod_ops_provider

    import httpx

    from .prod_ops import ArmClient, AzureProdOpsProvider

    arm = ArmClient(
        httpx.AsyncClient(timeout=30.0),
        identity_endpoint=identity_endpoint,
        identity_header=identity_header,
        client_id=client_id,
    )
    governed = os.environ.get("PROD_OPS_GOVERNED_APPS")
    apps = tuple(governed.split(",")) if governed else _DEFAULT_GOVERNED_APPS
    return AzureProdOpsProvider(
        arm,
        subscription_id=subscription_id,
        resource_group=os.environ.get("PROD_OPS_RESOURCE_GROUP", "rg-lunaris-prod"),
        api_app=os.environ.get("PROD_OPS_API_APP", "lunaris-prod-api"),
        governed_apps=apps,
        currency=os.environ.get("PROD_OPS_CURRENCY", "CAD"),
    )


def get_prod_ops_provider() -> IProdOpsProvider:
    """The prod-operations provider: the Azure ARM adapter in cloud, else the in-memory fake."""
    return _build_prod_ops_provider()


ProdOpsProviderDep = Annotated[IProdOpsProvider, Depends(get_prod_ops_provider)]


def _runtime_config_resolver(store: IUserConfigStore) -> ConfigResolver:
    """A per-run resolver over the per-user config store: user_id → {env-var name: value} for the
    model keys the user has set. Bound into the build's run-config scope so the build uses the
    tenant's chosen models; an unset key is omitted (→ the run-config env/default fallback)."""

    async def resolve(user_id: str) -> dict[str, str]:
        return to_env_map(await store.get_all(user_id=user_id))

    return resolve


def _byok_credential_resolver(vault: CredentialVault) -> CredentialResolver:
    """A per-run resolver over the vault: user_id → {env-var name: decrypted key} for keys they set.

    A provider the user hasn't set is omitted (its env-var key absent), so a missing required key
    surfaces as a refused build and an optional one degrades the capability honestly."""

    async def resolve(user_id: str) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for provider in BYOK_PROVIDERS:
            key = await vault.reveal(user_id=user_id, provider=provider)
            if key:
                resolved[KNOWN_SECRETS[provider]] = key
        return resolved

    return resolve


@lru_cache
def get_video_credential_resolver(settings: Settings) -> CredentialResolver | None:
    """The BYOK resolver the video worker renders each job's owner on (explainer-video V7-T1).

    Composed like the request-time vault (``get_credential_vault``) but OUTSIDE request DI — the
    worker (the lifespan task locally, the dedicated container in cloud) has no request to lean on,
    so it selects the store directly rather than through the ``Depends``-annotated getter, and is
    cached as a startup singleton. ``None`` when BYOK is off (no master key — local dev /
    single-user) → the render reads the process env, unchanged. In cloud the worker carries no
    provider keys, so this is what lets a keyed tenant's render authenticate as them; an unset key
    degrades honestly (silent voice, or a failed render with no LLM key), never billing a platform
    key."""
    cipher = _build_cipher(settings.key_enc_master)
    if cipher is None:
        return None
    store = _supabase_credential_store if settings.has_supabase else _in_memory_credential_store
    vault = CredentialVault(store=store, cipher=cipher, validator=get_secret_validator())
    return _byok_credential_resolver(vault)


@lru_cache
def _get_keyless_build_throttle(settings: Settings) -> KeylessBuildThrottle:
    """The process-wide keyless-build throttle for the given settings (T6).

    Cached on the frozen ``Settings`` value so the in-flight slot + per-day counts are shared across
    every build request for that config (per-request instances would never see each other's counts).
    Tracking the whole ``Settings`` (not just the Draft fields) is immune to config-surface drift;
    tests reset it via ``_get_keyless_build_throttle.cache_clear()`` (see the API conftest)."""
    return KeylessBuildThrottle(
        enabled=settings.draft_tier_enabled,
        daily_cap=settings.draft_daily_cap,
        max_concurrent=settings.draft_max_concurrent,
    )


# `get_course_service` + `CourseServiceDep` are defined at the end of this module: composing the
# service now depends on the per-course learner stores (progress/…) whose getters are declared
# further down, and a dependency default can only reference a callable already defined.

# One ConfigStore per config-file path (owns process env + the on-disk file), shared by requests.
# Tests override get_config_store.
_config_stores: dict[Path, ConfigStore] = {}


def get_config_store(settings: Annotated[Settings, Depends(get_settings)]) -> ConfigStore:
    """The process-wide non-secret config store for the configured config path."""
    path = settings.config_path
    if path not in _config_stores:
        _config_stores[path] = ConfigStore(path)
    return _config_stores[path]


ConfigStoreDep = Annotated[ConfigStore, Depends(get_config_store)]


def explain_is_available() -> bool:
    """Whether plain-language Explain can run on the HOSTED tier — an Anthropic key is reachable.

    Keyed on the environment variable (the unified runtime source, named once in ``KNOWN_SECRETS``):
    a key set in ``.env`` OR entered via the Settings UI (the SecretStore applies stored keys to
    ``os.environ``) both satisfy it. The keyless server-fallback tier is gated separately
    (``draft_tier_enabled``) — ``get_explain_binding`` resolves the two per request.
    """
    return bool(os.getenv(KNOWN_SECRETS["anthropic"]))


# One goal interpreter per process (built lazily on first availability), mirroring ``_explainer``.
# NOT cached as None — a key can be added at runtime via the Settings UI, so availability is
# re-checked each call: a present key returns the cached Claude client, an absent one the fallback.
_goal_interpreter: ClaudeGoalInterpreter | None = None


def get_goal_interpreter() -> IGoalInterpreter:
    """The brief interpreter behind the P7.5 clarifier (phase 1).

    The live Claude interpreter (worker tier) when an Anthropic key is reachable (same env source as
    Explain — a key in ``.env`` or the Settings UI), else a deterministic topic-derived fallback so
    the brief endpoint still renders the clarifier with sensible defaults without a key. The Claude
    client is lazy, so building it makes no network call; it is cached per process like Explain.
    """
    global _goal_interpreter
    if not explain_is_available():
        return DefaultGoalInterpreter()
    if _goal_interpreter is None:
        _goal_interpreter = ClaudeGoalInterpreter(os.getenv("LUNARIS_MODEL_WORKER", _WORKER_MODEL))
    return _goal_interpreter


GoalInterpreterDep = Annotated[IGoalInterpreter, Depends(get_goal_interpreter)]


@lru_cache
def _build_user_verifier(secret: str | None, supabase_url: str | None) -> IUserVerifier | None:
    """Compose the token verifier from config, cached per (secret, url) so the JWKS client's key
    cache is reused across requests instead of refetched each call.

    HS256 (local / shared secret) and asymmetric ES256/RS256 (cloud JWKS) can both be present; the
    composite routes each token to the right one by its header ``alg``. None when neither is set.
    """
    hs256 = JwtUserVerifier(secret) if secret else None
    asymmetric = JwksUserVerifier(supabase_url) if supabase_url else None
    if hs256 is None and asymmetric is None:
        return None
    return CompositeUserVerifier(hs256=hs256, asymmetric=asymmetric)


def get_jwt_verifier(
    settings: Annotated[Settings, Depends(get_settings)],
) -> IUserVerifier | None:
    """The end-user token verifier, or None when auth is unconfigured (fails closed with 503).

    The composition seam: HS256 for local/shared-secret, JWKS/ES256 for cloud — chosen per token by
    the composite, so ``require_user_id`` never depends on a concrete verifier.
    """
    return _build_user_verifier(settings.supabase_jwt_secret, settings.supabase_url)


JwtVerifierDep = Annotated[IUserVerifier | None, Depends(get_jwt_verifier)]

_UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}


def require_user_claims(
    verifier: JwtVerifierDep,
    authorization: Annotated[str | None, Header()] = None,
) -> UserClaims:
    """Authenticate the caller from the ``Authorization: Bearer`` token and return their claims.

    401 on a missing/malformed/invalid/expired token; 503 when no JWT secret is configured (a
    deployment error, not a client one). Binds ``user_id`` to the logging context so every
    downstream log line for the request carries it alongside ``request_id``/``run_id``.
    """
    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning("auth_failed", reason="missing_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers=_UNAUTHENTICATED_HEADERS,
        )
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = verifier.verify(token)
    except AuthError as exc:
        logger.warning("auth_failed", reason="invalid_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers=_UNAUTHENTICATED_HEADERS,
        ) from exc
    bind_contextvars(user_id=claims.user_id)
    return claims


CurrentUserClaimsDep = Annotated[UserClaims, Depends(require_user_claims)]


def require_user_id(
    verifier: JwtVerifierDep,
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """The authenticated caller's user id — the common case, where only the subject matters."""
    return require_user_claims(verifier, authorization).user_id


CurrentUserIdDep = Annotated[str, Depends(require_user_id)]


def require_admin(
    claims: CurrentUserClaimsDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """Authenticate the caller and require their email to be on the admin allowlist; returns the
    user id (to stamp on writes). 401 for a missing/invalid token (via ``require_user_claims``);
    403 for a valid token whose email is not an admin — so a non-admin can never reach the admin
    surface, and the failure mode is "not allowed", not "not found"."""
    if not settings.is_admin(claims.email):
        logger.warning("admin_denied", reason="not_in_allowlist")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return claims.user_id


AdminUserDep = Annotated[str, Depends(require_admin)]


def optional_user_id(
    verifier: JwtVerifierDep,
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    """The owner id for per-user data scoping — ``None`` when auth is not configured.

    The server-side mirror of the frontend ``AuthGate``: when auth is OFF (no verifier configured)
    this returns ``None`` so the user-data routes stay open and unscoped — byte-for-byte today's
    single-user behavior. When auth is ON it is mandatory: a missing/invalid token is a 401 (via
    ``require_user_id``), and a valid one yields the caller's id, which the service stamps on writes
    and filters reads by. So "optional" means *optional only while auth is unconfigured*, never a
    per-request opt-out once a deployment turns auth on.
    """
    if verifier is None:
        return None
    return require_user_id(verifier, authorization)


OptionalUserIdDep = Annotated[str | None, Depends(optional_user_id)]


# Progress stores follow the user-config posture: process-wide singletons, Supabase when keyed
# (durable, owner-scoped RLS), in-memory otherwise (offline dev / hermetic tests).
_in_memory_progress_store = InMemoryProgressStore()
_supabase_progress_store = SupabaseProgressStore()


def get_progress_store(
    settings: Annotated[Settings, Depends(get_settings)],
    owner_id: Annotated[str | None, Depends(optional_user_id)],
) -> IProgressStore:
    """The learner-progress store: Supabase (durable, owner-scoped RLS) for an authenticated
    caller when keyed; the in-memory fallback otherwise — including the auth-off single-user
    posture, where there is no user_id to scope Supabase rows by (the app_config precedent)."""
    if settings.has_supabase and owner_id is not None:
        return _supabase_progress_store
    return _in_memory_progress_store


ProgressStoreDep = Annotated[IProgressStore, Depends(get_progress_store)]


# Activity stores follow the progress-store posture: process-wide singletons, Supabase when keyed
# (durable, owner-scoped RLS), in-memory otherwise (offline dev / hermetic tests).
_in_memory_activity_store = InMemoryActivityStore()
_supabase_activity_store = SupabaseActivityStore()


def get_activity_store(
    settings: Annotated[Settings, Depends(get_settings)],
    owner_id: Annotated[str | None, Depends(optional_user_id)],
) -> IActivityStore:
    """The learning-telemetry store: Supabase (durable, owner-scoped RLS) for an authenticated
    caller when keyed; the in-memory fallback otherwise — including the auth-off single-user
    posture, where there is no user_id to scope Supabase rows by (the progress-store precedent)."""
    if settings.has_supabase and owner_id is not None:
        return _supabase_activity_store
    return _in_memory_activity_store


ActivityStoreDep = Annotated[IActivityStore, Depends(get_activity_store)]


# Bookmark stores follow the progress-store posture: process-wide singletons, Supabase when keyed
# (durable, owner-scoped RLS), in-memory otherwise (offline dev / hermetic tests).
_in_memory_bookmark_store = InMemoryBookmarkStore()
_supabase_bookmark_store = SupabaseBookmarkStore()


def get_bookmark_store(
    settings: Annotated[Settings, Depends(get_settings)],
    owner_id: Annotated[str | None, Depends(optional_user_id)],
) -> IBookmarkStore:
    """The bookmark store: Supabase (durable, owner-scoped RLS) for an authenticated caller when
    keyed; the in-memory fallback otherwise — including the auth-off single-user posture, where
    there is no user_id to scope Supabase rows by (the progress-store precedent)."""
    if settings.has_supabase and owner_id is not None:
        return _supabase_bookmark_store
    return _in_memory_bookmark_store


BookmarkStoreDep = Annotated[IBookmarkStore, Depends(get_bookmark_store)]


def get_learning_event_emitter(store: ActivityStoreDep) -> LearningEventEmitter:
    """The telemetry emitter the progress writes ride on — stateless over the activity store,
    so a fresh per-request instance is free."""
    return LearningEventEmitter(store)


LearningEventEmitterDep = Annotated[LearningEventEmitter, Depends(get_learning_event_emitter)]


async def get_explain_binding(
    owner_id: OptionalUserIdDep,
    vault: CredentialVaultDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ExplainBinding | None:
    """Resolve this request's explain capability: who answers, on which tier, under whose keys.

    The ladder mirrors the build pipeline's credential semantics:
    - **Vault caller (auth + BYOK):** their own keys become the call's credential scope —
      tenant-only, no env fallback. Their own Anthropic key → ``hosted``; none → the keyless
      ``server-fallback`` (when the Draft tier is on), never the platform key.
    - **No vault (auth off / single-user):** the process env decides — key → ``hosted``,
      else ``server-fallback`` when the Draft tier is on.
    - Neither tier available → ``None`` (the route fails closed with today's 503).

    Built fresh per request: the explainer's lazy model client would otherwise pin the first
    caller's key (the same BYOK invariant as the per-run pipeline factories).
    """
    credentials: Mapping[str, str] | None = None
    if vault is not None and owner_id is not None:
        credentials = await _byok_credential_resolver(vault)(owner_id)
        keyed = bool(credentials.get(KNOWN_SECRETS["anthropic"]))
    else:
        keyed = explain_is_available()
    if not keyed and not settings.draft_tier_enabled:
        return None
    explainer = ClaudeExplainer(os.getenv("LUNARIS_MODEL_WORKER", _WORKER_MODEL))
    return ExplainBinding(
        explainer=explainer,
        source="hosted" if keyed else "server-fallback",
        credentials=credentials,
    )


ExplainBindingDep = Annotated[ExplainBinding | None, Depends(get_explain_binding)]


@lru_cache
def _get_explain_throttle(settings: Settings) -> KeylessExplainThrottle:
    """One explain throttle per Settings — the per-user daily counts must be shared across
    requests (mirrors ``_get_keyless_build_throttle``; tests reset via ``cache_clear()``)."""
    return KeylessExplainThrottle(daily_cap=settings.explain_daily_cap)


def get_explain_throttle(
    settings: Annotated[Settings, Depends(get_settings)],
) -> KeylessExplainThrottle:
    """The shared daily cap for server-fallback explains (``LUNARIS_EXPLAIN_DAILY_CAP``)."""
    return _get_explain_throttle(settings)


ExplainThrottleDep = Annotated[KeylessExplainThrottle, Depends(get_explain_throttle)]


def get_course_service(
    settings: Annotated[Settings, Depends(get_settings)],
    run_store: Annotated[IRunStore, Depends(get_run_store)],
    registry: Annotated[RunRegistry, Depends(get_run_registry)],
    event_store: Annotated[IRunEventStore, Depends(get_run_event_store)],
    vault: CredentialVaultDep,
    user_config_store: UserConfigStoreDep,
    progress_store: ProgressStoreDep,
    bookmark_store: BookmarkStoreDep,
    activity_store: ActivityStoreDep,
) -> CourseService:
    """Compose the CourseService for the configured pipeline (overridable in tests)."""
    # Durable Postgres store when Supabase is configured (courses survive restarts + are shared
    # across replicas — the stateless-container need); the file store otherwise (offline dev).
    store = _resolve_course_store(settings)
    factory = _PIPELINE_FACTORIES.get(settings.pipeline)
    if factory is None:
        # An unrecognized LUNARIS_PIPELINE shouldn't silently run the paid live path; warn loudly.
        logger.warning("unknown_pipeline_falling_back", requested=settings.pipeline, default="live")
        factory = build_orchestrator
    # BYOK on (a vault is configured) → builds run on the caller's own keys; off → on the process
    # environment (admin/single-user), keeping today's behaviour.
    resolver = _byok_credential_resolver(vault) if vault is not None else None
    # Per-user config (model selection) when auth is on → builds run on the tenant's chosen models;
    # off → the process env / code defaults. Gated on has_auth (a verifier exists) — note this can
    # diverge from has_supabase: with a JWKS URL but no service-role key, the resolver is wired yet
    # the store is the in-memory fallback. Cheap to always wire (the store is lazy); the resolver
    # only fires for an owned build.
    config_resolver = _runtime_config_resolver(user_config_store) if settings.has_auth else None
    # Video generation (explainer-video V4) is gated by the operator kill-switch: wire the factory
    # only when it's on, so a build enqueues videos only where the operator opted in (dev now, prod
    # at V7). The per-build keyed + owner checks layer on top inside CourseService.
    video_coordinator_factory = (
        _video_coordinator_factory(get_video_job_queue(settings), get_video_storage(settings))
        if settings.video_generation_enabled
        else None
    )
    return CourseService(
        store,
        factory,
        run_store,
        registry,
        event_store,
        credential_resolver=resolver,
        config_resolver=config_resolver,
        video_coordinator_factory=video_coordinator_factory,
        # The course-deletion storage cascade (V7-T4) — wired unconditionally (independent of the
        # video gate) so an old course's artifacts are reclaimable even after video is turned off.
        video_job_queue=get_video_job_queue(settings),
        video_storage=get_video_storage(settings),
        # The learner-data cascade for a full course delete (course-delete): the caller's per-course
        # progress, bookmarks, and activity feed, so deleting a course purges them too. Owner-scoped
        # in the service.
        progress_store=progress_store,
        bookmark_store=bookmark_store,
        activity_store=activity_store,
        throttle=_get_keyless_build_throttle(settings),
        bridge_registry=_device_bridge_registry,
        bridge_limits=BridgeLimits(
            liveness_s=settings.device_bridge_liveness_s,
            completion_timeout_s=settings.device_bridge_completion_timeout_s,
        ),
    )


CourseServiceDep = Annotated[CourseService, Depends(get_course_service)]
